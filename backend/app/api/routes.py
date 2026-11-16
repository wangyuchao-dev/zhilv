"""HTTP 接口层。

路由顺序有讲究：固定路径（/stats、/task/{id}）必须写在 /{plan_id} 前面，
否则 "stats" 会被当成 plan_id 去做 int 转换，直接 422。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import LLM_API_KEY, SUPPORTED_CITIES
from app.database import get_db
from app.schemas.plan import (
    GenerateAck,
    PlanBrief,
    PlanDetail,
    PlanRequest,
    SavePlanRequest,
    TaskStatus,
)
from app.agents.chat_agent import ChatAgent
from app.schemas.plan import ExtractReply, ExtractRequest
from app.services.plan_service import RateLimited, ServiceBusy, plan_service

chat_agent = ChatAgent()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["travel"])


# ==================== 基础 ====================
@router.get("/health")
def health() -> dict:
    from app.core.cache import cache
    from app.database import engine
    from sqlalchemy import text

    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "down",
        "cache": cache.kind,
        # 没配 Key 时服务依然能起来，这里明确告诉运维是配置问题
        "llm_configured": bool(LLM_API_KEY.strip()),
    }


@router.get("/meta/options")
def meta_options() -> dict:
    """前端下拉框、多选框的选项，统一从后端给，避免前后端写两遍。"""
    return {
        "cities": SUPPORTED_CITIES,
        "travel_styles": ["自然风景", "拍照", "美食", "古镇", "休闲", "历史", "亲子", "夜生活"],
        "diets": ["少辣", "不吃香菜", "不吃葱", "素食", "清真"],
        "paces": ["轻松", "适中", "紧凑"],
        "hotel_levels": ["经济型", "舒适型", "高档"],
        "genders": ["男", "女", "不透露"],
    }


# ==================== 聊天抽槽位 ====================
@router.post("/chat/extract", response_model=ExtractReply)
def extract_from_chat(req: ExtractRequest) -> ExtractReply:
    """把一句话抽成表单字段。只抽「说了的」，没提的返回 null。"""
    return chat_agent.extract(req)


# ==================== 生成（异步） ====================
@router.post("/plans/generate", response_model=GenerateAck, status_code=202)
def generate_plan(req: PlanRequest, request: Request) -> GenerateAck:
    """提交生成任务。

    立刻返回：命中缓存时 status=done 且带 result；否则 status=running 带 task_id。
    202 表示「已接受，还在处理」。
    """
    ip = request.client.host if request.client else ""
    try:
        return plan_service.submit(req, client_ip=ip)
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except ServiceBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/plans/task/{task_id}", response_model=TaskStatus)
def get_task(task_id: str) -> dict:
    """前端每 800ms 轮询一次，看进度。done 时 result 一起返回。"""
    task = plan_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task


# ==================== 保存 / 历史 ====================
@router.post("/plans", response_model=PlanDetail)
def save_plan(payload: SavePlanRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return plan_service.save(db, payload)
    except Exception:
        # 详细信息只写日志，不返回给前端 —— 原始报错里可能有表名、字段名甚至连接串
        logger.exception(
            "保存行程失败 | user=%s dest=%s days=%s",
            payload.request.user_name,
            payload.request.destination,
            payload.request.days,
        )
        raise HTTPException(status_code=500, detail="保存失败，请稍后重试")


@router.get("/plans/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    return plan_service.stats(db)


@router.get("/plans", response_model=List[PlanBrief])
def list_plans(
    limit: int = Query(50, ge=1, le=200),
    destination: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[dict]:
    return plan_service.list_plans(db, limit=limit, destination=destination, keyword=keyword)


@router.get("/plans/{plan_id}", response_model=PlanDetail)
def get_plan(plan_id: int, db: Session = Depends(get_db)) -> dict:
    data = plan_service.get_plan(db, plan_id)
    if not data:
        raise HTTPException(status_code=404, detail="记录不存在")
    return data


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)) -> dict:
    ok = plan_service.delete_plan(db, plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"deleted": plan_id}
