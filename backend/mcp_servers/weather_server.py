"""天气 MCP Server（stdio）。

对外只暴露一个工具：get_weather(city, start_date, end_date)。
数据源用 open-meteo：免费、无需 Key、支持未来 16 天预报。

为什么不调它的 geocoding 接口反查经纬度：实测「大理」会匹配到
四川泸州的大理镇（28.6,105.4），不是云南大理（25.6,100.2）。
我们的城市是固定的 7 个，直接写死坐标更准也更快。

启动：python -m mcp_servers.weather_server
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

# 7 座城市的真实坐标（写死，避免同名地名匹配错）
CITY_COORDS = {
    "大连": (38.9140, 121.6147),
    "成都": (30.5728, 104.0668),
    "西安": (34.3416, 108.9398),
    "厦门": (24.4798, 118.0894),
    "三亚": (18.2528, 109.5119),
    "大理": (25.6065, 100.2676),
    "长沙": (28.2282, 112.9388),
}

# WMO 天气代码 → 中文，只映射常见几种
WMO = {
    0: "晴", 1: "少云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷阵雨", 96: "雷暴冰雹", 99: "雷暴冰雹",
}


@mcp.tool()
def get_weather(city: str, start_date: str, end_date: str) -> str:
    """查询某城市在指定日期区间的天气预报。

    Args:
        city: 城市名，必须是 大连/成都/西安/厦门/三亚/大理/长沙 之一
        start_date: 开始日期，格式 YYYY-MM-DD
        end_date: 结束日期，格式 YYYY-MM-DD

    Returns:
        JSON 字符串：{"city": ..., "days": [{date, desc, tmin, tmax, rain}]}
        城市不支持或超出预报范围时返回 {"error": "说明"}。
    """
    if city not in CITY_COORDS:
        return json.dumps(
            {"error": "暂不支持 %s 的天气查询（支持：%s）" % (city, "、".join(CITY_COORDS))},
            ensure_ascii=False,
        )

    lat, lon = CITY_COORDS[city]
    query = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "Asia/Shanghai",
    })
    url = "https://api.open-meteo.com/v1/forecast?" + query

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return json.dumps(
            {"error": "天气服务暂时不可用（%s）" % type(exc).__name__}, ensure_ascii=False
        )

    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        return json.dumps(
            {"error": "%s 在 %s 至 %s 暂无预报（预报只覆盖未来约 16 天）" % (city, start_date, end_date)},
            ensure_ascii=False,
        )

    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    rains = daily.get("precipitation_probability_max") or []
    codes = daily.get("weather_code") or []

    days = []
    for i, day in enumerate(dates):
        days.append({
            "date": day,
            "desc": WMO.get(codes[i] if i < len(codes) else -1, "未知"),
            "tmin": lows[i] if i < len(lows) else None,
            "tmax": highs[i] if i < len(highs) else None,
            "rain": rains[i] if i < len(rains) else None,
        })

    return json.dumps({"city": city, "days": days}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
