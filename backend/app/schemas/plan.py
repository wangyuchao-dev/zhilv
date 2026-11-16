"""接口的入参 / 出参结构。

输入侧字段参照老师给的参考页面，另外补上姓名和年龄（需求里要求的）。
输出侧是行程的结构化模型，同时充当大模型的「输出格式约束」。
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import SUPPORTED_CITIES

# ==================== 枚举 ====================
TravelStyle = Literal["自然风景", "拍照", "美食", "古镇", "休闲", "历史", "亲子", "夜生活"]
DietPref = Literal["少辣", "不吃香菜", "不吃葱", "素食", "清真"]
Pace = Literal["轻松", "适中", "紧凑"]
HotelLevel = Literal["经济型", "舒适型", "高档"]
Gender = Literal["男", "女", "不透露"]


# ==================== 输入：表单 ====================
class PlanRequest(BaseModel):
    """第一个页面提交上来的结构化需求。"""

    # ---- 基础信息 ----
    user_name: str = Field(..., min_length=2, max_length=20, description="姓名")
    age: int = Field(..., ge=6, le=80, description="年龄")
    gender: Gender = Field("不透露", description="性别")
    departure_city: str = Field("", max_length=30, description="出发城市，可空")

    # ---- 目的地与日期 ----
    destination: str = Field(..., min_length=2, max_length=20, description="目的地城市")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    days: int = Field(..., ge=1, le=5, description="旅行天数。每个城市收录 11-12 个景点，5 天以内质量最好")
    travelers: int = Field(..., ge=1, le=20, description="出行人数")

    # ---- 偏好设置 ----
    pace: Pace = Field("适中", description="节奏偏好")
    hotel_level: HotelLevel = Field("舒适型", description="住宿偏好")
    budget: int = Field(..., ge=300, le=200000, description="总预算，单位元")
    travel_style: List[TravelStyle] = Field(..., min_length=1, max_length=8, description="旅行偏好")
    diet: List[DietPref] = Field(default_factory=list, description="饮食偏好，可空")

    # ---- 额外 ----
    extra_request: str = Field("", max_length=200, description="额外要求")

    # ---------- 校验 ----------
    @field_validator("destination")
    @classmethod
    def _check_destination(cls, v: str) -> str:
        city = v.strip()
        if city not in SUPPORTED_CITIES:
            raise ValueError(f"目的地只支持：{'、'.join(SUPPORTED_CITIES)}")
        return city

    @field_validator("travel_style")
    @classmethod
    def _dedup_style(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for item in v:
            if item not in out:
                out.append(item)
        if not out:
            raise ValueError("旅行偏好至少选一个")
        return out

    @model_validator(mode="after")
    def _check_dates(self) -> "PlanRequest":
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        real_days = (self.end_date - self.start_date).days + 1

        # 关键：object.__setattr__ 会绕过字段级的 le=5 校验。
        # 如果只在这里纠正、不再判一次上限，前端传 days=3 但日期跨 17 天时，
        # 字段校验用 3 通过，随后被改成 17，等于后端也放行了超长行程。
        if real_days > 5:
            raise ValueError(
                f"当前行程 {real_days} 天，最多支持 5 天，请缩短日期"
            )

        if real_days != self.days:
            # 以日期为准，自动纠正天数，避免前端算错导致前后不一致
            object.__setattr__(self, "days", real_days)
        return self

    # ---------- 辅助 ----------
    def cache_key(self) -> str:
        """同样的需求算同一个 key，用于缓存命中。"""
        import hashlib
        import json

        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def to_prompt_text(self) -> str:
        """给大模型看的需求描述。"""
        lines = [
            f"出行人：{self.user_name}，{self.age} 岁，{self.gender}",
            f"出发地：{self.departure_city or '未填写'}",
            f"目的地：{self.destination}",
            f"日期：{self.start_date} 至 {self.end_date}，共 {self.days} 天",
            f"人数：{self.travelers} 人",
            f"节奏：{self.pace}",
            f"住宿：{self.hotel_level}",
            f"总预算：{self.budget} 元（约人均 {self.budget // max(self.travelers, 1)} 元）",
            f"旅行偏好：{'、'.join(self.travel_style)}",
            f"饮食偏好：{'、'.join(self.diet) if self.diet else '无特殊要求'}",
            f"额外要求：{self.extra_request or '无'}",
        ]
        return "\n".join(lines)


# ==================== 输出：结构化行程 ====================
class SlotPlan(BaseModel):
    """一个时段（上午 / 下午 / 晚上）。"""

    spot: str = Field(description="景点或活动名称，必须来自参考材料")
    activity: str = Field(description="这个时段具体做什么，一到两句话")
    duration: str = Field(description="建议停留时长，例如 2 小时")
    ticket: str = Field(description="门票信息，例如 免费 / 180元/人")


class MealPlan(BaseModel):
    lunch: str = Field(description="午餐推荐：店名或菜品 + 人均价格")
    dinner: str = Field(description="晚餐推荐：店名或菜品 + 人均价格")


class DayPlan(BaseModel):
    day: int = Field(description="第几天，从 1 开始")
    date: str = Field(description="这一天的具体日期，格式 YYYY-MM-DD")
    theme: str = Field(description="这一天的主线，六个字以内")
    morning: SlotPlan
    afternoon: SlotPlan
    evening: SlotPlan
    meals: MealPlan
    accommodation: str = Field(description="住宿区域 + 价位建议")
    tips: str = Field(description="这一天的注意事项，一句话")


class BudgetBreakdown(BaseModel):
    transport: int = Field(description="交通费用，整数，单位元")
    hotel: int = Field(description="住宿费用，整数，单位元")
    food: int = Field(description="餐饮费用，整数，单位元")
    ticket: int = Field(description="门票费用，整数，单位元")
    other: int = Field(description="其他杂费，整数，单位元")
    total: int = Field(description="合计，必须等于上面五项之和")
    per_person: int = Field(description="人均，total 除以出行人数后取整")


class SourceRef(BaseModel):
    title: str = Field(description="命中的章节标题")
    source: str = Field(description="来源文件名")


class TravelPlanBody(BaseModel):
    """大模型要产出的完整行程。sources 由程序回填，不让模型编。"""

    summary: str = Field(description="一句话概括这份行程，40 字以内")
    highlights: List[str] = Field(description="这次行程的三个亮点")
    budget: BudgetBreakdown
    daily_plans: List[DayPlan] = Field(description="逐日安排，天数必须与需求一致")
    packing_tips: List[str] = Field(description="行李与出行提示，3 到 5 条")


class PlanResponse(BaseModel):
    """一次完整生成的结果。"""

    task_id: str
    cached: bool = Field(False, description="是否命中缓存")
    elapsed_ms: int = 0
    summary: str
    highlights: List[str] = []
    budget: Optional[BudgetBreakdown] = None
    daily_plans: List[DayPlan] = []
    packing_tips: List[str] = []
    sources: List[SourceRef] = []
    weather: List[WeatherDay] = []


class ExtractedFields(BaseModel):
    """一轮对话能确认的字段，没提到的一律 None。"""

    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days: Optional[int] = None
    travelers: Optional[int] = None
    budget: Optional[float] = None
    travel_style: Optional[List[str]] = None
    pace: Optional[Literal["轻松", "适中", "紧凑"]] = None
    hotel_level: Optional[Literal["经济型", "舒适型", "高档"]] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ExtractRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    history: List[ChatTurn] = []
    draft: dict = Field(default_factory=dict)


class ExtractReply(BaseModel):
    fields: ExtractedFields
    reply: str = Field(..., max_length=200)
    missing: List[str] = []


class WeatherDay(BaseModel):
    """一天预报，来自天气 MCP。"""

    date: str
    desc: str
    tmin: Optional[float] = None
    tmax: Optional[float] = None
    rain: Optional[int] = None


class GenerateAck(BaseModel):
    """提交生成后的回执。

    生成要十几秒，接口不能一直挂着，所以立刻返回一个 task_id，
    前端拿它去轮询 /plans/task/{id}。

    例外：命中缓存时直接带 result 返回（status=done），前端不用轮询。
    """

    task_id: str
    status: Literal["running", "done", "failed"] = "running"
    step: str = ""
    progress: int = Field(0, description="0-4，对应四个阶段")
    cached: bool = False
    result: Optional[PlanResponse] = None


class TaskStatus(BaseModel):
    """轮询返回的任务状态。"""

    task_id: str
    status: Literal["running", "done", "failed"]
    step: str = ""
    progress: int = 0
    error: str = ""
    elapsed_ms: int = 0
    result: Optional[PlanResponse] = None


# ==================== 保存 / 历史 ====================
class SavePlanRequest(BaseModel):
    """第二个页面点保存时提交。"""

    request: PlanRequest
    plan: TravelPlanBody
    sources: List[SourceRef] = []
    # 把生成时拿到的 task_id 一起存下来，方便以后反查是哪次生成的结果
    task_id: str = ""
    # 天气存进 plan_json，历史详情也能看到
    weather: List[WeatherDay] = []


class PlanBrief(BaseModel):
    """历史列表的一条。"""

    id: int
    user_name: str
    destination: str
    start_date: Optional[str] = None
    days: int
    travelers: int
    hotel_level: str = ""
    travel_style: List[str] = []
    summary: str = ""
    created_at: Optional[str] = None


class PlanDetail(PlanBrief):
    """历史详情。"""

    age: int = 0
    gender: str = "不透露"
    departure_city: str = ""
    pace: str = ""
    budget: int = 0
    diet: List[str] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    extra_request: str = ""
    plan: dict = {}
    sources: List[SourceRef] = []
