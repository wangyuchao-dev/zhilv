"""天气 MCP 客户端。

用 mcp 官方 SDK 起一个 stdio 子进程连 weather_server，调 get_weather 工具。
没装 langchain-mcp-adapters 也能用 —— 那个包会强制 langchain-core>=1.0，
把我们锁定的 0.3.29 顶掉，实测会把整条链拖升级，所以不用它。

任何异常都吞掉返回空串：天气是锦上添花，不能因为它挂了就整份行程失败。
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# backend/mcp_servers/weather_server.py
SERVER = Path(__file__).resolve().parents[2] / "mcp_servers" / "weather_server.py"


async def _call(city: str, start_date: str, end_date: str) -> tuple[str, list]:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_weather",
                {"city": city, "start_date": start_date, "end_date": end_date},
            )
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return _parse("\n".join(texts).strip())


def _parse(raw: str) -> tuple[str, list]:
    """把 server 返回的 JSON 拆成两份：给模型的文本 + 给前端展示的结构。"""
    try:
        data = json.loads(raw)
    except Exception:
        return "", []

    if data.get("error"):
        return data["error"], []

    city = data.get("city", "")
    days = data.get("days") or []
    lines = ["%s 天气预报：" % city]
    for d in days:
        lines.append("%s %s %s~%s℃ 降水概率%s%%" % (
            d.get("date"), d.get("desc"), d.get("tmin"), d.get("tmax"), d.get("rain")
        ))
    return "\n".join(lines), days


def fetch_weather(city: str, start_date: str, end_date: str, timeout: float = 15.0) -> tuple[str, list]:
    """同步入口：给 Service 层调用。失败返回 ("", [])，不抛异常。"""
    try:
        return asyncio.run(asyncio.wait_for(_call(city, start_date, end_date), timeout))
    except Exception as exc:
        logger.warning("天气查询失败（%s: %s），本次不带天气", type(exc).__name__, str(exc)[:80])
        return "", []
