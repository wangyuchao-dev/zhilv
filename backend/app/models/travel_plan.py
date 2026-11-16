"""行程记录表。

一条记录 = 一次完整需求 + 一次生成结果。
表单字段原样存一份，生成的结构化 JSON 存一份，
历史页直接读这张表，不用再调模型。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class TravelPlan(Base):
    __tablename__ = "travel_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(40), index=True, default="")

    # ==================== 基础信息 ====================
    user_name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int] = mapped_column(Integer, default=0)
    gender: Mapped[str] = mapped_column(String(10), default="不透露")
    departure_city: Mapped[str] = mapped_column(String(50), default="")

    # ==================== 目的地与日期 ====================
    destination: Mapped[str] = mapped_column(String(50), index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days: Mapped[int] = mapped_column(Integer, default=3)
    travelers: Mapped[int] = mapped_column(Integer, default=1)

    # ==================== 偏好 ====================
    pace: Mapped[str] = mapped_column(String(20), default="适中")
    hotel_level: Mapped[str] = mapped_column(String(20), default="舒适型")
    budget: Mapped[int] = mapped_column(Integer, default=0)
    travel_style: Mapped[list] = mapped_column(JSON, default=list)
    diet: Mapped[list] = mapped_column(JSON, default=list)

    # ==================== 额外 ====================
    extra_request: Mapped[str] = mapped_column(Text, default="")

    # ==================== 生成结果 ====================
    summary: Mapped[str] = mapped_column(String(300), default="")
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # ==================== 时间 ====================
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<TravelPlan id={self.id} {self.destination} {self.days}天>"

    # ---------- 序列化 ----------
    def brief(self) -> dict:
        """列表页用，不返回整个 plan_json。"""
        return {
            "id": self.id,
            "user_name": self.user_name,
            "destination": self.destination,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "days": self.days,
            "travelers": self.travelers,
            "hotel_level": self.hotel_level,
            "travel_style": self.travel_style or [],
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_dict(self) -> dict:
        """详情页用完整数据。"""
        plan = self.plan_json or {}
        return {
            "id": self.id,
            "task_id": self.task_id,
            "user_name": self.user_name,
            "age": self.age,
            "gender": self.gender,
            "departure_city": self.departure_city,
            "destination": self.destination,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "days": self.days,
            "travelers": self.travelers,
            "pace": self.pace,
            "hotel_level": self.hotel_level,
            "budget": self.budget,
            "travel_style": self.travel_style or [],
            "diet": self.diet or [],
            "extra_request": self.extra_request,
            "summary": self.summary,
            "plan": plan,
            # 来源是跟着 plan 一起存进去的，这里提到顶层，前端不用再往下挖
            "sources": plan.get("sources", []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
