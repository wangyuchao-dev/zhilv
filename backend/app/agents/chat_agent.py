"""聊天侧槽位抽取：把人话变成表单字段。

和 PlannerAgent 一样用 with_structured_output，但目的相反：
    Planner  让模型「编内容」（景点、餐厅、价格）
    Chat     让模型「读事实」（用户到底说了什么）

所以温度压到 0，prompt 反复强调「没提到就是 null」——
补一个默认日期，整份行程都会跟着错。
"""
from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from app.config import SUPPORTED_CITIES
from app.core.llm import get_llm
from app.schemas.plan import ExtractReply, ExtractRequest

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """你是行程助手的槽位抽取器。从用户这句话里读出「行程相关」的字段。

铁律：
1. 用户没提到的字段必须返回 null，**绝对不要补默认值或猜测**。
2. 只抽行程字段。人名、称呼、寒暄、身份介绍一律忽略：
   「我是赵哥」不是 1 个人；「你好」不产生任何字段。
3. 数字要对上下文：「预算 688」是总预算 688 元；「我一个人」是人数 1；「玩三天」是天数 3。
4. 用户说「改成 X」「换成 X」时，只返回这次改的字段，其余 null。
5. 字段对应关系（必须落到对应字段，不要只在回复里提）：
   「偏好 / 喜欢 / 想玩 X」→ travel_style: ["X"]
   「预算 X」→ budget
   「X 个人 / 我一个人 / 我们俩」→ travelers
   「玩 X 天 / X 日游」→ days
   「住得好一点 / 要五星」→ hotel_level
6. 日期能确定年份就输出 YYYY-MM-DD；只说「12月12日」这种没年份的，
   start_date 输出 12-12（不带年份），交给前端补。
7. 目的地只支持这几座城市：{cities}。
   用户说别的城市（比如北京、上海）时，destination 必须返回 null，
   并在回复里说明「目前还没收录」，不要硬填。

表单当前值（只用来理解「改成…」在改什么，不要直接回填）：
{draft}

之前聊过：
{history}

用户这句话：{message}

另外用一句 50 字内的话回复用户：说清识别到什么、还缺什么，别客套。
必填项：目的地、出发日期、返程日期、人数、预算、偏好。
"""


class ChatAgent:
    def __init__(self) -> None:
        # with_structured_output 要挂在 llm 上，再接 prompt；
        # 挂在 (prompt | llm) 这个 sequence 后面不会报错，但传 dict 会炸。
        prompt = ChatPromptTemplate.from_messages([("system", EXTRACT_PROMPT)])
        self._chain = prompt | get_llm(temperature=0.0).with_structured_output(ExtractReply)

    def extract(self, req: ExtractRequest) -> ExtractReply:
        history_text = "无"
        if req.history:
            history_text = "\n".join(
                "%s：%s" % ("用户" if t.role == "user" else "助手", t.content)
                for t in req.history[-6:]
            )

        # 只把有值的字段给模型看，避免它把空字符串当成"用户说的"
        draft = {k: v for k, v in (req.draft or {}).items() if v not in (None, "", [])}

        result = self._chain.invoke({
            "draft": draft or "（表单还是空的）",
            "history": history_text,
            "message": req.message,
            "cities": "、".join(SUPPORTED_CITIES),
        })

        # 二次校验：模型偶尔不听 prompt，这里兜一道
        dest = result.fields.destination
        if dest and dest not in SUPPORTED_CITIES:
            result.fields.destination = None
            result.reply = "「%s」还没收录，目前只支持 %s。换一个？" % (
                dest, "、".join(SUPPORTED_CITIES)
            )

        return result
