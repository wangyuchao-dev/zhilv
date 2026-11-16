import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

CHROMA_DB_DIR_RAW = Path(os.getenv("CHROMA_DB_DIR", "db/chroma_db"))
CHROMA_DB_DIR = (
    CHROMA_DB_DIR_RAW
    if CHROMA_DB_DIR_RAW.is_absolute()
    else BACKEND_DIR / CHROMA_DB_DIR_RAW
)
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "travel_guides")

# ===================== 以下为新增配置 =====================

# ---------- 对话模型 ----------
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen-flash")

# ---------- 数据库 ----------
# 有 PostgreSQL 就填 PG 的连接串；没有就用 SQLite，代码完全一样
# 例：postgresql+psycopg://postgres:postgres@127.0.0.1:5432/zhilv
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./db/zhilv.db")

# ---------- Redis ----------
# 留空则自动退化成进程内内存缓存，接口不变
REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_ENABLED = bool(REDIS_URL.strip())

# ---------- 检索 ----------
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "6"))

# 相关性阈值。低于这个分数的检索结果直接丢掉，防止把无关内容喂给模型。
#
# 实测（text-embedding-v4 + 当前 7 城语料，21 次真实检索 / 105 个片段）：
#   语料里明确有答案   0.892 - 0.920
#   Agent 真实查询     0.807 - 0.858
#   语料里根本没有     0.730 - 0.786  （最高 0.7863）
# 0.80 正好卡在 0.7863 和 0.8070 之间的缝里。
# ⚠ 换 embedding 模型、加城市或大改语料后，分数会整体漂移，必须重测这个值。
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.80"))

# 降级阈值：正常检索命中太少时才用，只放宽绝对阈值、不放大 top_k。
# 降级次数会写进日志，频繁触发就说明 MIN_SCORE 该重调了。
# 0.79 而非 0.75：实测无关问题 top1 落在 0.730-0.786，
# 0.75 会把 5/7 个无关查询整批放回，等于把 0.80 刚挡住的洞又打开。
# 0.79 仍卡在「无关最高 0.7863」和「有用最低 0.807」之间。
MIN_SCORE_FALLBACK = float(os.getenv("MIN_SCORE_FALLBACK", "0.79"))

# 降级时最多保留几条（宁可少给，不硬塞）
MAX_FALLBACK_CHUNKS = int(os.getenv("MAX_FALLBACK_CHUNKS", "1"))

# 同时在跑的生成任务上限，超了直接回 503，别让用户干等
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "2"))
MIN_CHUNKS = int(os.getenv("MIN_CHUNKS", "2"))

# ---------- 缓存 ----------
PLAN_CACHE_TTL = int(os.getenv("PLAN_CACHE_TTL", "1800"))   # 结果缓存 30 分钟
WEATHER_TTL = int(os.getenv("WEATHER_TTL", "10800"))         # 天气 3 小时（预报本来就一天几更）
RETR_TTL = int(os.getenv("RETR_TTL", "1800"))                # 检索结果 30 分钟
TASK_TTL = int(os.getenv("TASK_TTL", "3600"))               # 任务状态 1 小时

# ---------- 可选目的地 ----------
SUPPORTED_CITIES = [
    "大连", "成都", "西安", "厦门", "三亚", "大理", "长沙",
]
