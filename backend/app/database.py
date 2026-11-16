"""数据库连接与 Session 管理。

同一套代码既能跑 SQLite 也能跑 PostgreSQL：
    SQLite     DATABASE_URL=sqlite:///./db/zhilv.db
    PostgreSQL DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/zhilv

切库只改 .env，模型和业务代码一行都不用动。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BACKEND_DIR, DATABASE_URL


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


_IS_SQLITE = DATABASE_URL.startswith("sqlite")

# SQLite 要允许跨线程；PG 不需要，并且 PG 建议开 pool_pre_ping 防连接失效
_connect_args = {"check_same_thread": False} if _IS_SQLITE else {}

# SQLite 用相对路径时要保证目录存在
if _IS_SQLITE and "///" in DATABASE_URL:
    _db_path = DATABASE_URL.split("///", 1)[1]
    if _db_path and not _db_path.startswith(":memory:"):
        (BACKEND_DIR / _db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
    pool_pre_ping=not _IS_SQLITE,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db():
    """FastAPI 依赖：每个请求一个 Session，用完必关。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表。启动时调一次。"""
    from app.models import travel_plan  # noqa: F401  必须导入模型才会注册到 Base

    Base.metadata.create_all(bind=engine)
