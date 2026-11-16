"""RAG 检索层。

写入那段在 vector_db.py 里已经有了，这里补的是「读」：
    - 按城市过滤，避免问大连混进成都的攻略
    - 支持多个 query 分别检索后合并去重（需求解析 Agent 会给出 3 条 query）
    - 返回相似度分数，低于阈值的丢掉，防止把无关内容喂给模型
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import md5
from pathlib import Path
from typing import List

from app.config import BACKEND_DIR, MIN_SCORE, RETR_TTL, RETRIEVAL_TOP_K
from app.core.cache import cache
from app.rag.vector_db import build_embeddings, get_chroma_collection


# 余弦距离 → 相似度。cosine distance 越小越像，转成 0~1 的分数方便判断。
# 阈值从 config 来，别在这里写死 —— 调参要改配置不该改代码。
_MIN_SCORE = MIN_SCORE


@dataclass
class RetrievedChunk:
    title: str
    source: str
    text: str
    score: float = 0.0

    def as_context(self) -> str:
        """拼进 prompt 的格式。"""
        return f"【{self.source} · {self.title}】\n{self.text}"

    def as_source(self) -> dict:
        return {"title": self.title, "source": self.source}


@dataclass
class RetrievalResult:
    chunks: List[RetrievedChunk] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)

    def as_context(self) -> str:
        if not self.chunks:
            return "（没有检索到相关资料）"
        return "\n\n".join(
            f"[{i}] {c.as_context()}" for i, c in enumerate(self.chunks, 1)
        )

    def as_sources(self) -> List[dict]:
        seen, out = set(), []
        for c in self.chunks:
            key = (c.source, c.title)
            if key in seen:
                continue
            seen.add(key)
            out.append(c.as_source())
        return out


def _city_filter(city: str) -> dict | None:
    """把城市名映射成 md 文件名。语料是 dalian_guide.md 这种格式。"""
    mapping = {
        "大连": "dalian_guide.md",
        "成都": "chengdu_guide.md",
        "西安": "xian_guide.md",
        "厦门": "xiamen_guide.md",
        "三亚": "sanya_guide.md",
        "大理": "dali_guide.md",
        "长沙": "changsha_guide.md",
    }
    filename = mapping.get(city)
    if not filename:
        return None
    return {"source": filename}


def retrieve(
    query: str,
    top_k: int = 0,
    city: str | None = None,
    min_score: float = _MIN_SCORE,
) -> List[RetrievedChunk]:
    """单条 query 检索。"""
    top_k = top_k or RETRIEVAL_TOP_K

    embeddings = build_embeddings()
    collection = get_chroma_collection()
    if embeddings is None or collection is None:
        return []

    try:
        vector = embeddings.embed_query(query)
        where = _city_filter(city) if city else None
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        print(f"[retriever] 检索失败：{type(exc).__name__}: {exc}")
        return []

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    chunks: List[RetrievedChunk] = []
    for doc, meta, dist in zip(docs, metas, dists):
        # 切分时会产出一个只有标题的碎块（比如「# 2026大连深度游玩全攻略」），
        # 这种块向量上很容易命中，但对生成没有任何价值，直接丢掉
        if len((doc or "").strip()) < 40:
            continue
        # cosine 距离范围 0~2，转成相似度
        score = max(0.0, 1.0 - float(dist) / 2.0)
        if score < min_score:
            continue
        meta = meta or {}
        chunks.append(
            RetrievedChunk(
                title=str(meta.get("title", "")),
                source=str(meta.get("source", "")),
                text=doc,
                score=round(score, 4),
            )
        )
    return chunks


def _corpus_version() -> str:
    """语料指纹：7 个 md 的 mtime + size 一起哈希。

    放进缓存 key 里，改了任何一份攻略缓存自动失效，
    不用手动去 Redis 里删 key —— 否则演示时会出「答的和资料对不上」。
    """
    try:
        files = sorted((BACKEND_DIR / "data").glob("*.md"))
        sig = "|".join(f"{p.name}:{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in files)
    except Exception:
        sig = "unknown"
    return md5(sig.encode()).hexdigest()[:8]


def _retr_key(queries: List[str], city: str | None, top_k: int, min_score: float) -> str:
    q = "|".join(sorted(x.strip() for x in queries if x.strip()))
    return "retr:%s:%d:%.3f:%s:%s" % (
        city or "-", top_k, min_score,
        _corpus_version(), md5(q.encode()).hexdigest()[:10],
    )


def retrieve_multi(
    queries: List[str],
    top_k: int = 0,
    city: str | None = None,
    min_score: float | None = None,
) -> RetrievalResult:
    """多条 query 分别检索，按文本去重后合并。

    需求解析 Agent 通常会给 3 条 query：景点、餐饮住宿、行程节奏。
    分开查比拼成一条长句效果好，因为向量检索对长句不敏感。

    min_score 传 None 时走默认的 MIN_SCORE；降级重查时传一个更低的值。
    """
    top_k = top_k or RETRIEVAL_TOP_K
    ms = _MIN_SCORE if min_score is None else min_score

    # 先查缓存：key 含 city / top_k / 阈值 / 语料指纹 / query 集合，
    # 少任何一个都会串结果
    cache_key = _retr_key(queries, city, top_k, ms)
    hit = cache.get(cache_key)
    if hit:
        return RetrievalResult(
            chunks=[RetrievedChunk(**c) for c in hit["chunks"]],
            queries=hit.get("queries") or list(queries),
        )

    seen: dict[str, RetrievedChunk] = {}

    for q in queries:
        if not q.strip():
            continue
        kwargs = {} if min_score is None else {"min_score": min_score}
        for chunk in retrieve(q, top_k=top_k, city=city, **kwargs):
            # 注意：这个变量原来叫 key，和上面的缓存 key 撞了，
            # 导致 cache.set 写进去的是一段正文而不是 retr:xxx
            dedup_key = chunk.text[:120]
            if dedup_key not in seen or chunk.score > seen[dedup_key].score:
                seen[dedup_key] = chunk

    ranked = sorted(seen.values(), key=lambda c: c.score, reverse=True)[:top_k]
    result = RetrievalResult(chunks=ranked, queries=list(queries))

    # 空结果不缓存 —— 可能是 embedding 抖动，存了会一直拿到空
    if ranked:
        cache.set(cache_key, {
            "chunks": [
                {"title": c.title, "source": c.source, "text": c.text, "score": c.score}
                for c in ranked
            ],
            "queries": list(queries),
        }, RETR_TTL)

    return result
