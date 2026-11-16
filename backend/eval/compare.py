"""对比两份评测结果，输出涨跌。

用法：
    python eval/compare.py result_v1-baseline.json result_v2-xxx.json
    python eval/compare.py result_e2e_v1.json result_e2e_v2.json

会自动识别是「检索评测」还是「端到端评测」，选对应的指标对比。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent


def load(name: str) -> dict:
    p = EVAL_DIR / name if not Path(name).is_absolute() else Path(name)
    if not p.exists():
        p = EVAL_DIR / (name if name.endswith(".json") else name + ".json")
    return json.loads(p.read_text(encoding="utf-8"))


def pct(v):
    return "%.1f%%" % (v * 100) if isinstance(v, float) else v


def diff(label, before, after, better="up"):
    if before == after:
        mark = "  =  "
    else:
        up = after > before if isinstance(after, (int, float)) else False
        good = up if better == "up" else (not up)
        mark = " ✓↑ " if good else " ✗↓ "
    print("  %-22s %-14s → %-14s %s" % (label, pct(before), pct(after), mark))


def compare_retrieval(a, b):
    sa, sb = a["summary"], b["summary"]
    print("检索评测对比   %s  →  %s" % (sa["version"], sb["version"]))
    print("-" * 66)
    diff("检索命中率", sa["recall_at_k"], sb["recall_at_k"])
    diff("平均 top1", sa["avg_top1"], sb["avg_top1"])
    print("  %-22s %-14s → %-14s" % ("整题通过", sa["passed"], sb["passed"]))
    print("  %-22s %-14s → %-14s" % ("兜底识别", sa["neg_ok"], sb["neg_ok"]))

    ra = {r["id"]: r for r in a["rows"]}
    rb = {r["id"]: r for r in b["rows"]}
    regress, improve = [], []
    for qid in sorted(set(ra) & set(rb)):
        x, y = ra[qid], rb[qid]
        if x["recall"] is None:
            continue
        dx = y["recall"] - x["recall"]
        if dx < -0.001:
            regress.append((qid, x["query"], x["recall"], y["recall"]))
        elif dx > 0.001:
            improve.append((qid, x["query"], x["recall"], y["recall"]))
    if improve:
        print("\n  变好 %d 题:" % len(improve))
        for qid, q, x, y in improve[:8]:
            print("    %-8s %-24s %.0f%% → %.0f%%" % (qid, q[:22], x * 100, y * 100))
    if regress:
        print("\n  变差 %d 题（重点看）:" % len(regress))
        for qid, q, x, y in regress[:8]:
            print("    %-8s %-24s %.0f%% → %.0f%%" % (qid, q[:22], x * 100, y * 100))


def compare_e2e(a, b):
    sa, sb = a["summary"], b["summary"]
    print("端到端对比   %s  →  %s" % (sa["version"], sb["version"]))
    print("-" * 66)

    def ratio(s):
        x, y = s["content_hit"].split("/")
        return int(x) / int(y) if int(y) else 0

    def r_ok(s):
        x, y = s["struct_ok"].split("/")
        return int(x) / int(y)
    diff("结构合规率", r_ok(sa), r_ok(sb))
    diff("内容命中率", ratio(sa), ratio(sb))
    diff("judge 均分", sa["judge_avg"], sb["judge_avg"])
    diff("平均耗时(s)", sa["avg_elapsed"], sb["avg_elapsed"], better="down")
    print("  %-22s %-14s → %-14s" % ("预算合理", sa["budget_ok"], sb["budget_ok"]))
    print("  %-22s %-14s → %-14s" % ("跑偏违规", sa["violations"], sb["violations"]))

    ra = {r["id"]: r for r in a["rows"]}
    rb = {r["id"]: r for r in b["rows"]}
    common = [i for i in sorted(set(ra) & set(rb)) if "judge_avg" in ra[i] and "judge_avg" in rb[i]]
    if not common:
        return
    print("\n  逐例 judge 变化:")
    for cid in common:
        x, y = ra[cid]["judge_avg"], rb[cid]["judge_avg"]
        mark = "=" if abs(y - x) < 0.05 else ("↑" if y > x else "↓")
        print("    %-9s %-18s %.2f → %.2f  %s" % (cid, ra[cid]["name"][:16], x, y, mark))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    if "cases" in a["summary"]:
        compare_e2e(a, b)
    else:
        compare_retrieval(a, b)
