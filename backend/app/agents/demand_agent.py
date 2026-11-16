"""Agent 1：需求解析。

职责单一 —— 把「用户填的表单」翻译成「检索指令」。

为什么要单独一个 Agent？
    直接把整段表单丢给向量库，检索效果很差：向量模型对长句不敏感，
    而且用户的偏好（比如「亲子」）需要转成具体的检索意图（海洋公园、室内景点）。
    这一步让模型来判断「该查什么」，比让程序拼字符串准得多。
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.schemas.plan import PlanRequest


class SearchPlan(BaseModel):
    """需求解析的产出。"""

    queries: List[str] = Field(
        description="3 条检索查询，每条 5-14 个字，必须包含城市名"
    )
    focus: str = Field(
        description="这次行程的重点，一句话，给后续排行程做指针"
    )
    avoid: List[str] = Field(
        default_factory=list,
        description="应该避开的安排，0-3 条。比如带小孩建议避开夜间长距离移动",
    )


DEMAND_PROMPT = """你是一个旅游需求分析师。用户填好了一张出行需求表，你要把它翻译成检索指令。

【用户需求】
{requirement}

【你的任务】
1. 生成正好 3 条检索查询，分别对应下面三个方向：
   - 第 1 条：景点（结合用户的旅行偏好，挑对应的景点类型）
   - 第 2 条：餐饮与住宿（结合饮食偏好和住宿档次）
   - 第 3 条：行程节奏与实用信息（结合节奏快慢、人数、年龄）
2. 每条查询 5-14 个字，必须包含「{city}」两个字，像人在搜索框里输入的那样短
3. focus：一句话说清这次行程应该重点安排什么
4. avoid：这个用户应该避开什么，0-3 条，没有就给空列表

【注意】
- 查询要具体。写「{city} 亲子 海洋公园」比写「{city} 适合孩子的景点推荐」好
- 不要写成完整句子，不要带标点
- avoid 要基于实际约束（年龄、节奏、饮食），不要编理由
"""


class DemandAgent:
    """把表单转成检索计划。"""

    def __init__(self) -> None:
        self._chain = get_llm(temperature=0.2).with_structured_output(SearchPlan)

    def analyze(self, req: PlanRequest) -> SearchPlan:
        # 规则放 system，需求放 human。city 这种短变量直接替换，
        # 需求全文不塞进 system，免得 system 每次都不一样、失去稳定前缀的作用
        system = DEMAND_PROMPT.replace("{city}", req.destination).replace(
            "{requirement}", "（见下方用户需求）"
        )
        human = f"{req.to_prompt_text()}\n\n请按要求输出检索计划。"

        result = self._chain.invoke([("system", system), ("human", human)])
        if isinstance(result, dict):
            result = SearchPlan(**result)

        # 兜底：模型没给查询时用规则拼
        if not result.queries:
            result.queries = [
                f"{req.destination} {' '.join(req.travel_style[:2])} 景点",
                f"{req.destination} 美食 住宿",
                f"{req.destination} {req.pace} 行程",
            ]
        return result
