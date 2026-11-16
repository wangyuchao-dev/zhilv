"""应用入口。

启动：
    cd backend
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.logging import setup_logging
from app.database import init_db


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表（已存在会跳过）
    init_db()
    yield


app = FastAPI(
    title="知旅 · 智能旅行规划系统",
    description="RAG Agent 驱动的行程规划：结构化输入 → 需求解析 → 攻略检索 → 行程编排 → 结构化输出",
    version="1.0.0",
    lifespan=lifespan,
)

# 带凭证时浏览器不接受 allow_origins=["*"]，必须写具体源。
# 前端 dev server 是 5173，两个写法都收进来。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"service": "zhilv", "name": "知旅 · 智能旅行规划系统", "docs": "/docs"}
