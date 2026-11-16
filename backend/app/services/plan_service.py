"""行程服务：业务编排层。

Router 只负责收请求和返回响应，所有业务逻辑都在这里：
    查缓存 → 在途去重 → 限流 → 建任务 → Agent1 → RAG → Agent2 → 落缓存 → (可选)落库

Redis / 内存缓存的用途：
    结果缓存   plan:cache:{hash}      同样的表单不重复调模型
    任务状态   plan:task:{id}         前端轮询进度
    生成结果   plan:result:{id}       轮询到 done 时直接取
    在途锁     plan:inflight:{hash}   同一表单并发提交只跑一次
    降级计数   stats:fallback:{date}  频繁降级 = 阈值该重测了
    接口限流   rate:{ip}
"""
from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.agents.demand_agent import DemandAgent
from app.agents.planner_agent import PlannerAgent
from app.config import (
    MAX_FALLBACK_CHUNKS,
    MAX_INFLIGHT,
    MIN_CHUNKS,
    MIN_SCORE_FALLBACK,
    PLAN_CACHE_TTL,
    TASK_TTL,
    WEATHER_TTL,
)
from app.core.cache import cache
from app.models.travel_plan import TravelPlan
from app.rag.retriever import retrieve_multi
from app.tools.weather import fetch_weather
from app.schemas.plan import (
    GenerateAck, PlanRequest, PlanResponse, SavePlanRequest, SourceRef,
)

logger = logging.getLogger(__name__)

# 生成是同步阻塞的（调模型），放到后台线程跑，接口才能立刻返回。
# 2 个并发够用：再多也是一起抢模型配额，反而都变慢。
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="plan-gen")

RATE_LIMIT = 20       # 每 IP 每分钟最多几次生成
RATE_WINDOW = 60      # 秒
INFLIGHT_TTL = 180    # 在途锁兜底过期（正常情况下任务结束就删）


class RateLimited(Exception):
    """触发了限流。"""


class ServiceBusy(Exception):
    """在途任务已满，不该让用户排队干等。"""


class PlanService:
    """业务编排。Agent 懒加载，避免 import 时就构造模型客户端。"""

    def __init__(self) -> None:
        # 不在 import 阶段构造 ChatTongyi：没配 Key 时服务应该还能起来、
        # /api/health 还能告诉我们「模型未配置」，而不是进程直接崩。
        self._demand: DemandAgent | None = None
        self._planner: PlannerAgent | None = None
        self._active = 0
        self._lock = threading.Lock()

    # 用普通方法而不是 @property：项目里统一这种写法，也方便看出「这里可能初始化」
    def _get_demand(self) -> DemandAgent:
        if self._demand is None:
            self._demand = DemandAgent()
        return self._demand

    def _get_planner(self) -> PlannerAgent:
        if self._planner is None:
            self._planner = PlannerAgent()
        return self._planner

    # ==================== 限流 ====================
    def _check_rate(self, ip: str) -> None:
        if not ip:
            return
        count = cache.incr(f"rate:{ip}", RATE_WINDOW)
        if count > RATE_LIMIT:
            raise RateLimited(f"请求太频繁了，每分钟最多生成 {RATE_LIMIT} 次")

    # ==================== 天气 ====================
    def _weather(self, req: PlanRequest) -> tuple[str, list]:
        """查天气（带缓存）。失败返回 ("", [])，绝不抛异常。"""
        wkey = "weather:%s:%s:%s" % (
            req.destination, req.start_date.isoformat(), req.end_date.isoformat()
        )
        hit = cache.get(wkey)
        if hit:
            logger.info("天气缓存命中 | %s | %d 天", wkey, len(hit["days"]))
            return hit["text"], hit["days"]

        text, days = fetch_weather(
            req.destination, req.start_date.isoformat(), req.end_date.isoformat()
        )
        # 只在真拿到数据时写；失败不缓存，否则一次抖动会挂 3 小时
        if days:
            cache.set(wkey, {"text": text, "days": days}, WEATHER_TTL)
            logger.info("天气已获取 | %s %d 天", req.destination, len(days))
        return text, days

    # ==================== 任务状态 ====================
    def _set_task(
        self, task_id: str, status: str, step: str, progress: int,
        error: str = "", elapsed_ms: int = 0,
    ) -> None:
        cache.set(
            f"plan:task:{task_id}",
            {
                "task_id": task_id,
                "status": status,
                "step": step,
                "progress": progress,
                "error": error,
                "elapsed_ms": elapsed_ms,
            },
            TASK_TTL,
        )

    def get_task(self, task_id: str) -> Optional[dict]:
        """轮询用。完成时把结果一起带上，省得前端再发一次请求。

        注意用深拷贝：内存缓存返回的是存储对象的引用，
        直接往里塞 result 会污染缓存里的任务字典（Redis 模式不会），
        造成两种后端行为不一致 —— 这种 bug 只在开发时看不见、上线才发现。
        """
        raw = cache.get(f"plan:task:{task_id}")
        if not raw:
            return None
        task = copy.deepcopy(raw)
        if task.get("status") == "done":
            task["result"] = cache.get(f"plan:result:{task_id}")
        return task

    # ==================== 生成（异步） ====================
    def submit(self, req: PlanRequest, client_ip: str = "") -> GenerateAck:
        """提交生成任务，立刻返回。

        命中缓存直接带 result（status=done）；已有相同任务在跑就复用它的 task_id；
        否则返回新 task_id，前端拿它去查 /plans/task/{id}。
        """
        hash_key = req.cache_key()
        cache_key = f"plan:cache:{hash_key}"
        inflight_key = f"plan:inflight:{hash_key}"

        # ① 缓存命中 —— 走这里不计限流，连点演示缓存效果不会被 429
        hit = cache.get(cache_key)
        if hit:
            return GenerateAck(
                task_id=uuid.uuid4().hex[:16],
                status="done",
                step="命中缓存",
                progress=4,
                cached=True,
                result=PlanResponse(**hit),
            )

        # ② 同样的表单已经在生成 —— 直接复用，避免双击烧两次 token
        running = cache.get(inflight_key)
        if running:
            return GenerateAck(
                task_id=running, status="running", step="已有相同任务在生成", progress=0
            )

        # ③ 限流（缓存命中和在途复用都不算）
        self._check_rate(client_ip)

        # ④ 活跃任务上限，满了直接说忙，别让请求在队列里静默排队
        with self._lock:
            if self._active >= MAX_INFLIGHT:
                raise ServiceBusy("生成任务正忙，请稍后再试")
            self._active += 1

        task_id = uuid.uuid4().hex[:16]
        self._set_task(task_id, "running", "排队中", 0)
        cache.set(inflight_key, task_id, INFLIGHT_TTL)

        try:
            _EXECUTOR.submit(self._run_generation, task_id, req, cache_key, inflight_key)
        except Exception:
            with self._lock:
                self._active = max(0, self._active - 1)
            cache.delete(inflight_key)
            raise

        return GenerateAck(task_id=task_id, status="running", step="排队中", progress=0)

    def _run_generation(
        self, task_id: str, req: PlanRequest, cache_key: str, inflight_key: str
    ) -> None:
        """后台真正干活的地方。状态写缓存，前端轮询读取。"""
        t0 = time.time()
        try:
            # ---- ① Agent 1：表单 → 检索计划 ----
            self._set_task(task_id, "running", "正在解析需求", 1)
            search_plan = self._get_demand().analyze(req)

            # ---- ② RAG 检索 + ③ 查天气：互不依赖，并行跑 ----
            self._set_task(task_id, "running", "正在检索攻略", 2)
            # 阈值 0.80 会砍掉长尾 chunk，候选要取比目标素材量更多
            top_k = max(8, req.days * 3)

            # 串行要 4~6 秒（检索 1~3s + 天气 3s），并行只取两者较大的那个
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_retr = pool.submit(retrieve_multi, search_plan.queries, top_k, req.destination)
                f_weather = pool.submit(self._weather, req)
                retrieval = f_retr.result()
                weather_text, weather_days = f_weather.result()

            # 素材太少时降级一次。行程规划场景里目的地一定在语料内，
            # 所以空检索是异常（阈值误杀 / embedding 故障），不是「用户问了没答案」。
            # 0.79 仍卡在无关最高 0.7863 之上，且只保留 top-1 —— 宁可少给，不把
            # 0.80 刚挡住的一整批无关内容捡回来。
            if len(retrieval.chunks) < MIN_CHUNKS:
                day_key = f"stats:fallback:{datetime.now():%Y%m%d}"
                n = cache.incr(day_key, ttl=7 * 86400)
                logger.warning(
                    "检索降级 | 今日第 %d 次 | task=%s dest=%s 命中=%d 条，"
                    "阈值 0.80 → %s 重查；频繁触发说明 MIN_SCORE 该重测了",
                    n, task_id, req.destination, len(retrieval.chunks), MIN_SCORE_FALLBACK,
                )
                retrieval = retrieve_multi(
                    search_plan.queries,
                    city=req.destination,
                    top_k=top_k,
                    min_score=MIN_SCORE_FALLBACK,
                )
                retrieval.chunks = retrieval.chunks[:MAX_FALLBACK_CHUNKS]

            # ---- ④ Agent 2：需求 + 素材 + 天气 → 结构化行程 ----
            self._set_task(task_id, "running", "正在编排行程", 3)
            body = self._get_planner().plan(
                req, retrieval, search_plan.focus, search_plan.avoid, weather_text
            )

            elapsed = int((time.time() - t0) * 1000)
            resp = PlanResponse(
                task_id=task_id,
                cached=False,
                elapsed_ms=elapsed,
                summary=body.summary,
                highlights=body.highlights,
                budget=body.budget,
                daily_plans=body.daily_plans,
                packing_tips=body.packing_tips,
                sources=[SourceRef(**s) for s in retrieval.as_sources()],
                weather=weather_days,
            )

            # ---- ④ 结果落缓存 + 存一份给轮询取 ----
            payload = resp.model_dump(mode="json")
            cache.set(cache_key, payload, PLAN_CACHE_TTL)
            cache.set(f"plan:result:{task_id}", payload, TASK_TTL)
            self._set_task(task_id, "done", "完成", 4, elapsed_ms=elapsed)

            logger.info(
                "生成完成 | task=%s dest=%s days=%s 耗时=%dms",
                task_id, req.destination, req.days, elapsed,
            )

        except Exception as exc:
            logger.exception(
                "生成行程失败 | task=%s dest=%s days=%s",
                task_id, req.destination, req.days,
            )
            self._set_task(
                task_id, "failed", "生成失败", -1,
                error=f"{type(exc).__name__}: {str(exc)[:120]}",
                elapsed_ms=int((time.time() - t0) * 1000),
            )
        finally:
            # 无论成功失败都要放行，否则活跃计数和在途锁会永久卡住
            with self._lock:
                self._active = max(0, self._active - 1)
            cache.delete(inflight_key)

    # ==================== 保存 ====================
    def save(self, db: Session, payload: SavePlanRequest) -> dict:
        req = payload.request
        plan_dict = payload.plan.model_dump(mode="json")
        plan_dict["sources"] = [s.model_dump() for s in payload.sources]
        plan_dict["weather"] = [w.model_dump() for w in payload.weather]

        row = TravelPlan(
            task_id=payload.task_id,
            user_name=req.user_name,
            age=req.age,
            gender=req.gender,
            departure_city=req.departure_city,
            destination=req.destination,
            start_date=req.start_date,
            end_date=req.end_date,
            days=req.days,
            travelers=req.travelers,
            pace=req.pace,
            hotel_level=req.hotel_level,
            budget=req.budget,
            travel_style=req.travel_style,
            diet=req.diet,
            extra_request=req.extra_request,
            summary=payload.plan.summary,
            plan_json=plan_dict,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.to_dict()

    # ==================== 查询 ====================
    def list_plans(
        self,
        db: Session,
        limit: int = 50,
        destination: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[dict]:
        stmt = select(TravelPlan)
        if destination:
            stmt = stmt.where(TravelPlan.destination == destination)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                TravelPlan.user_name.like(like) | TravelPlan.summary.like(like)
            )
        stmt = stmt.order_by(desc(TravelPlan.created_at)).limit(limit)
        rows = db.execute(stmt).scalars().all()
        return [r.brief() for r in rows]

    def get_plan(self, db: Session, plan_id: int) -> Optional[dict]:
        row = db.get(TravelPlan, plan_id)
        return row.to_dict() if row else None

    def delete_plan(self, db: Session, plan_id: int) -> bool:
        row = db.get(TravelPlan, plan_id)
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True

    # ==================== 统计（历史页顶部用） ====================
    def stats(self, db: Session) -> dict:
        # 只让数据库返回 4 个数字，不把整张表搬进内存
        row = db.execute(
            select(
                func.count(TravelPlan.id),
                func.count(func.distinct(TravelPlan.destination)),
                func.avg(TravelPlan.days),
                func.sum(TravelPlan.travelers),
            )
        ).one()

        total, cities, avg_days, travelers = row
        return {
            "total": int(total or 0),
            "cities": int(cities or 0),
            "avg_days": round(float(avg_days), 1) if avg_days else 0,
            "total_travelers": int(travelers or 0),
        }


# 全局单例。现在只是个空壳，第一次真正生成时才会构造模型客户端。
plan_service = PlanService()
