"""LLM-as-judge：用一次模型调用给行程质量打分。

为什么需要它：结构合规、预算合理这些能用规则判，但「安排得合不合理」「内容空不空」
只能靠模型判。用同一个模型自评有偏差，所以只作为**四个维度之一**，不单独当结论。
"""
from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm import get_llm

JUDGE_PROMPT = """你是旅行行程的评审。给下面这份行程打分，只看四件事。

【用户需求】
{request}

【生成的行程】
{plan}

四个维度，各 1-5 分（3 分是"能用但有明显问题"）：

1. relevance   相关性：景点和餐厅是否贴合用户的偏好、预算档次
2. feasibility 可行性：每天的时段安排是否冲突、是否过赶（一天跑五个景点算不合理）
3. specificity 具体性：是否有具体景点名、具体价格，而不是"当地美食""某公园"这种泛称
4. coherence   连贯性：同一天的安排是否在地理上顺路，主题是否统一

严格打分，不要都给 4-5 分。理由写成一句话，指出最主要的问题。
"""


class JudgeResult(BaseModel):
    relevance: int = Field(..., ge=1, le=5)
    feasibility: int = Field(..., ge=1, le=5)
    specificity: int = Field(..., ge=1, le=5)
    coherence: int = Field(..., ge=1, le=5)
    reason: str = Field(..., max_length=200)

    @property
    def avg(self) -> float:
        return round((self.relevance + self.feasibility + self.specificity + self.coherence) / 4, 2)


_chain = ChatPromptTemplate.from_messages([("system", JUDGE_PROMPT)]) | get_llm(
    temperature=0.0
).with_structured_output(JudgeResult)


def judge(request_text: str, plan_obj) -> JudgeResult:
    plan_json = json.dumps(plan_obj.model_dump(mode="json"), ensure_ascii=False)
    # 行程 JSON 可能几千字，截断到 3500 字够判断，也能压成本
    if len(plan_json) > 3500:
        plan_json = plan_json[:3500] + "…（截断）"
    return _chain.invoke({"request": request_text, "plan": plan_json})
