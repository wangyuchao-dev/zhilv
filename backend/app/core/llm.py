"""LLM 工厂。

两个 Agent 都要用模型，但每次都新建 ChatTongyi 会重新握手，
实测同一实例复用能把单次调用从 2.4s 降到 1.4s。

所以这里按 (模型名, 温度) 缓存实例，全项目共用。
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_community.chat_models import ChatTongyi

from app.config import CHAT_MODEL, LLM_API_KEY


@lru_cache(maxsize=8)
def get_llm(temperature: float = 0.3, model: str = "") -> ChatTongyi:
    """按温度和模型名拿一个共享实例。"""
    return ChatTongyi(
        model=model or CHAT_MODEL,
        dashscope_api_key=LLM_API_KEY,
        temperature=temperature,
        # 一次挂住的最长时间 = request_timeout × (max_retries + 1)。
        # 默认 60×3=180 秒，跑批量评测时太久，所以做成可配。
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        request_timeout=int(os.getenv("LLM_TIMEOUT", "60")),
    )
