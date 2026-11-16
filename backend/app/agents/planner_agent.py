"""Agent 2：行程编排。

拿到 RAG 素材后，把它排成一份逐日的、带预算的结构化行程。

为什么用 with_structured_output 而不是让模型自由发挥再解析 JSON？
    自由输出会漏字段、缺层级、数字对不上。
    Pydantic 结构约束 + function calling 能让模型「按 schema 填」，
    解析失败的概率从三成降到几乎为零。
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import List

from app.core.llm import get_llm
from app.rag.retriever import RetrievalResult
from app.schemas.plan import PlanRequest, TravelPlanBody


logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """你是一个资深行程规划师。根据用户需求和本地攻略资料，排一份可以直接执行的行程。

【硬性规则，必须全部遵守】
1. 景点、餐厅、住宿信息必须来自下方【攻略资料】。资料里没有的，写「资料未提及」。
   绝对不许虚构店名、门票价格、营业时间 —— 用户会真的照着走。
   例外：返程、休息、自由活动、逛商圈这类不属于景点，可以直接写，不要写成「资料未提及」。
2. daily_plans 数组的长度必须正好是 {days}，少一天都不行。
   每天都要有 morning / afternoon / evening 三个时段，不能留空。
   如果素材里的景点不够填满，允许安排「自由活动」「逛街」「休息」「返程」，
   但天数绝对不能少。最后一天的 evening 通常是返程。
3. 每天的 date 从 {start_date} 开始，逐日递增，格式 YYYY-MM-DD。
4. 预算：transport + hotel + food + ticket + other 必须等于 total；
   per_person = total ÷ {travelers} 后取整。总额要贴近用户给的 {budget} 元。
5. summary 40 字以内；highlights 正好 3 条；packing_tips 3 到 5 条。
6. 【硬性，输出前自查】同一天的 morning.spot、afternoon.spot、evening.spot
   必须是三个**互不相同**的值，绝对不允许出现两段相同的地点名。
   这是最容易违反的一条，写完 daily_plans 后逐个 day 检查一遍。
   不同天之间也尽量不重复同一个地方。
   如果确实需要同一地点，必须写出**不同时段的不同玩法**
   （比如上午看海鸥、傍晚看跨海大桥日落），且 activity 必须完全不同。
   晚上优先安排餐饮、夜市、商圈，不要硬塞景点。
   注意：每个城市收录 17-18 个景点，天数不超过 5 天，素材是够用的。

【用户偏好，排行程时要体现】
- 节奏：{pace}（轻松就少排点，紧凑就多排点，别把一天塞满）
- 住宿档位：{hotel_level}
- 旅行偏好：{styles}
- 饮食禁忌：{diet}（推荐餐厅时必须避开）
"""


class PlannerAgent:
    """把需求和素材排成结构化行程。"""

    def __init__(self) -> None:
        # 温度 0.5 时实测偶发把 daily_plans 数组写崩
        # （第二个元素写成 "2": [...]，JSON 直接不合法）。
        # 这里准备 3 个逐次降温的实例：第一次用 0.3 保证行程不死板，
        # 一旦解析失败就换更低的温度重试 —— 越重试越保守，比同温度重复有效。
        self._chains = [
            get_llm(temperature=t).with_structured_output(TravelPlanBody)
            for t in (0.3, 0.2, 0.1)
        ]

    # 后置覆写：模型只管内容，能从入参算出来的字段一律由程序定
    # —— 日期按 start_date 推、序号重排、预算合计按分项求和
    def _post_override(self, body, req) -> None:
        for i, day in enumerate(body.daily_plans, start=1):
            day.day = i
            day.date = req.start_date + timedelta(days=i - 1)

        b = body.budget
        if b is not None:
            b.total = round(b.transport + b.hotel + b.food + b.ticket + b.other, 2)
            b.per_person = round(b.total / max(1, req.travelers), 2)

    def plan(
        self,
        req: PlanRequest,
        retrieval: RetrievalResult,
        focus: str = "",
        avoid: List[str] | None = None,
        weather: str = "",
    ) -> TravelPlanBody:
        system = PLANNER_SYSTEM.format(
            days=req.days,
            start_date=req.start_date.isoformat(),
            travelers=req.travelers,
            budget=req.budget,
            pace=req.pace,
            hotel_level=req.hotel_level,
            styles="、".join(req.travel_style),
            diet="、".join(req.diet) if req.diet else "无特殊禁忌",
        )

        avoid_text = "、".join(avoid) if avoid else "无"
        human = f"""【用户需求】
{req.to_prompt_text()}

【这次行程的重点】
{focus or '按用户偏好正常安排'}

【要避开的安排】
{avoid_text}

【出行期间天气】
{weather or '暂无天气数据，按常规季节准备'}

【攻略资料】
{retrieval.as_context()}

请按 schema 输出完整行程。"""

        # 结构化输出偶发会解析失败（模型把嵌套数组写崩）。
        # 三次机会，温度 0.3 → 0.2 → 0.1，实测能把失败率压到接近 0。
        last_error: Exception | None = None
        messages = [("system", system), ("human", human)]

        for attempt, chain in enumerate(self._chains):
            try:
                body = chain.invoke(messages)
                self._post_override(body, req)
                return body
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "行程结构化输出失败（第 %d 次 / 温度 %s）| dest=%s days=%s | %s",
                    attempt + 1, (0.3, 0.2, 0.1)[attempt],
                    req.destination, req.days, type(exc).__name__,
                )
                if attempt < len(self._chains) - 1:
                    time.sleep(0.5)

        raise RuntimeError(f"行程生成失败（已重试 3 次）：{last_error}")
