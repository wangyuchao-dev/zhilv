"""检索层评测：跑 30 道题，算命中率和兜底识别率。

用法：
    cd backend
    python eval/run_eval.py                    # 默认版本名 = 当前日期
    python eval/run_eval.py v2-加BM25           # 指定版本名，便于前后对比

指标：
    recall@9    所有关键要素的命中比例（最细）
    整题通过    一道题的关键要素全中的题数
    兜底识别    语料答不了的题，top1 分数是否低于阈值
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import MIN_SCORE                      # noqa: E402
from app.rag.retriever import retrieve_multi          # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
TOP_K = 9


def run(version: str) -> dict:
    questions = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))["questions"]

    rows = []
    for q in questions:
        result = retrieve_multi([q["query"]], city=q["city"], top_k=TOP_K)
        text = "\n".join(c.text for c in result.chunks)
        hits = [m for m in q["must"] if m in text]
        rows.append({
            "id": q["id"],
            "city": q["city"],
            "query": q["query"],
            "negative": q["negative"],
            "must": q["must"],
            "hits": hits,
            "n": len(result.chunks),
            "top1": round(result.chunks[0].score, 4) if result.chunks else 0.0,
            "recall": (len(hits) / len(q["must"])) if q["must"] else None,
        })

    pos = [r for r in rows if not r["negative"]]
    neg = [r for r in rows if r["negative"]]

    total_must = sum(len(r["must"]) for r in pos)
    total_hit = sum(len(r["hits"]) for r in pos)
    passed = sum(1 for r in pos if len(r["hits"]) == len(r["must"]))
    neg_ok = sum(1 for r in neg if r["top1"] < MIN_SCORE or r["n"] == 0)

    summary = {
        "version": version,
        "date": date.today().isoformat(),
        "threshold": MIN_SCORE,
        "top_k": TOP_K,
        "recall_at_k": round(total_hit / total_must, 4) if total_must else 0,
        "must_hit": "%d/%d" % (total_hit, total_must),
        "passed": "%d/%d" % (passed, len(pos)),
        "neg_ok": "%d/%d" % (neg_ok, len(neg)),
        "avg_top1": round(sum(r["top1"] for r in rows) / len(rows), 4),
    }

    # ---------- 控制台表格 ----------
    print("=" * 78)
    print("检索评测  %s  |  阈值 %.2f  |  每题取 top-%d" % (version, MIN_SCORE, TOP_K))
    print("=" * 78)
    print("%-8s %-5s %-26s %4s %7s %8s" % ("ID", "城市", "问题", "条数", "top1", "命中"))
    print("-" * 78)
    for r in rows:
        mark = "兜底" if r["negative"] else "%d/%d" % (len(r["hits"]), len(r["must"]))
        flag = ""
        if r["negative"]:
            flag = "✓" if (r["top1"] < MIN_SCORE or r["n"] == 0) else "✗ 高分召回"
        print("%-8s %-5s %-26s %4d %7.3f %8s %s" % (
            r["id"], r["city"], r["query"][:24], r["n"], r["top1"], mark, flag))

    print("-" * 78)
    print("检索命中率  %s  (%.1f%%)" % (summary["must_hit"], summary["recall_at_k"] * 100))
    print("整题通过    %s" % summary["passed"])
    print("兜底识别    %s" % summary["neg_ok"])
    print("平均 top1   %.3f" % summary["avg_top1"])

    # ---------- 保存 ----------
    out = EVAL_DIR / ("result_%s.json" % version)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\n结果已存: %s" % out.name)
    return summary


if __name__ == "__main__":
    ver = sys.argv[1] if len(sys.argv) > 1 else "v%d" % len(list(EVAL_DIR.glob("result_*.json"))) + "-当前"
    run(ver)
