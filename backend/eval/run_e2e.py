"""端到端评测：一个完整需求跑完整条链路，四类打分。

链路和线上一致：Agent1 → 检索（含降级） → 天气 → Agent2 → 后置覆写。
不走 HTTP，直接调内部方法，省掉服务启动和轮询。

用法：
    python eval/run_e2e.py                # 全部 12 个
    python eval/run_e2e.py --limit 4      # 只跑前 4 个（分批防超时）
    python eval/run_e2e.py v2-xxx         # 指定版本名
"""
from __future__ import annotations

import json
import os
import sys
import time

# 必须在 import app.* 之前设，get_llm 是 lru_cache，晚了就不生效
os.environ.setdefault("LLM_TIMEOUT", "25")
os.environ.setdefault("LLM_MAX_RETRIES", "1")
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.agents.demand_agent import DemandAgent          # noqa: E402
from app.agents.planner_agent import PlannerAgent       # noqa: E402
from app.config import MIN_CHUNKS, MIN_SCORE_FALLBACK, MAX_FALLBACK_CHUNKS  # noqa: E402
from app.rag.retriever import retrieve_multi            # noqa: E402
from app.schemas.plan import PlanRequest                # noqa: E402
from app.tools.weather import fetch_weather             # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))
from judge import judge                                 # noqa: E402


def run_one(case: dict, demand: DemandAgent, planner: PlannerAgent, use_weather: bool = False) -> dict:
    req = PlanRequest(**case["request"])
    t0 = time.time()

    plan = demand.analyze(req)
    retrieval = retrieve_multi(plan.queries, city=req.destination, top_k=max(8, req.days * 3))

    # 和线上一致的降级：素材不足时放宽阈值重查
    fallback = False
    if len(retrieval.chunks) < MIN_CHUNKS:
        fallback = True
        retrieval = retrieve_multi(plan.queries, city=req.destination,
                                   top_k=max(8, req.days * 3), min_score=MIN_SCORE_FALLBACK)
        retrieval.chunks = retrieval.chunks[:MAX_FALLBACK_CHUNKS]

    # 天气默认跳过：MCP 每次起子进程 3 秒且偶发超时，会把 12 个用例拖成十几分钟。
    # 天气链路已单独验证（写入 352 字符、TTL 10800、命中日志），不重复测。
    if use_weather:
        weather_text, weather_days = fetch_weather(
            req.destination, req.start_date.isoformat(), req.end_date.isoformat()
        )
    else:
        weather_text, weather_days = "", []

    body = planner.plan(req, retrieval, plan.focus, plan.avoid, weather_text)
    elapsed = time.time() - t0

    # ---------- ① 结构 ----------
    struct_ok = True
    struct_issues = []
    if len(body.daily_plans) != req.days:
        struct_ok = False
        struct_issues.append("天数 %d≠%d" % (len(body.daily_plans), req.days))
    for i, day in enumerate(body.daily_plans):
        expect_date = req.start_date + timedelta(days=i)
        if day.date != expect_date:
            struct_ok = False
            struct_issues.append("D%d 日期 %s≠%s" % (i + 1, day.date, expect_date))
            break
    b = body.budget
    parts = b.transport + b.hotel + b.food + b.ticket + b.other
    if abs(parts - b.total) > 1.0:
        struct_ok = False
        struct_issues.append("合计 %.0f≠分项和 %.0f" % (b.total, parts))

    # ---------- ② 内容 ----------
    text = json.dumps(body.model_dump(mode="json"), ensure_ascii=False)
    exp = case["expect"]
    must = exp.get("must_include", [])
    hits = [m for m in must if m in text]
    violations = [m for m in exp.get("must_avoid", []) if m in text]

    # ---------- ③ 预算 ----------
    budget_ok = b.total <= exp.get("budget_max", float("inf"))

    # ---------- ④ 质量 ----------
    jr = judge(req.to_prompt_text(), body)

    return {
        "id": case["id"], "name": case["name"], "city": req.destination,
        "struct_ok": struct_ok, "struct_issues": struct_issues,
        "content_hit": len(hits), "content_total": len(must),
        "violations": violations, "budget_ok": budget_ok,
        "total": b.total, "budget_max": exp.get("budget_max"),
        "chunks": len(retrieval.chunks), "fallback": fallback,
        "weather": len(weather_days),
        "judge": jr.model_dump(mode="json"), "judge_avg": jr.avg,
        "elapsed": round(elapsed, 1),
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    version = args[0] if args else "e2e-当前"
    limit = None
    use_weather = False
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            limit = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
        elif a == "--weather":
            use_weather = True

    cases = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))["cases"]
    start = 0
    for a in sys.argv[1:]:
        if a.startswith("--start"):
            start = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    if start:
        cases = cases[start:]
    if limit:
        cases = cases[:limit]

    demand, planner = DemandAgent(), PlannerAgent()
    rows = []
    for i, case in enumerate(cases, 1):
        print("[%d/%d] %s ..." % (i, len(cases), case["name"]), flush=True)
        try:
            rows.append(run_one(case, demand, planner, use_weather))
        except Exception as exc:
            print("  失败: %s: %s" % (type(exc).__name__, str(exc)[:100]), flush=True)
            rows.append({"id": case["id"], "name": case["name"], "error": str(exc)[:120]})
        # 增量落盘：即使后面卡住被杀，前面的结果还在
        (EVAL_DIR / ("progress_%s.json" % version)).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [r for r in rows if "error" not in r]
    if not ok:
        print("全部失败")
        return

    print()
    print("=" * 96)
    print("%-9s %-20s %5s %6s %5s %6s %6s" % ("ID", "用例", "结构", "内容", "预算", "judge", "耗时"))
    print("-" * 96)
    for r in rows:
        if "error" in r:
            print("%-9s %-20s  ❌ %s" % (r["id"], r["name"][:18], r["error"][:40]))
            continue
        print("%-9s %-20s %5s %4d/%-2d %5s %6.2f %5.1fs" % (
            r["id"], r["name"][:18],
            "✓" if r["struct_ok"] else "✗",
            r["content_hit"], r["content_total"],
            "✓" if r["budget_ok"] else "✗",
            r["judge_avg"], r["elapsed"]))

    summary = {
        "version": version, "cases": len(ok),
        "struct_ok": "%d/%d" % (sum(1 for r in ok if r["struct_ok"]), len(ok)),
        "content_hit": "%d/%d" % (sum(r["content_hit"] for r in ok), sum(r["content_total"] for r in ok)),
        "budget_ok": "%d/%d" % (sum(1 for r in ok if r["budget_ok"]), len(ok)),
        "violations": sum(len(r["violations"]) for r in ok),
        "judge_avg": round(sum(r["judge_avg"] for r in ok) / len(ok), 2),
        "avg_elapsed": round(sum(r["elapsed"] for r in ok) / len(ok), 1),
        "fallback_cases": sum(1 for r in ok if r["fallback"]),
        "weather_cases": sum(1 for r in ok if r["weather"] > 0),
    }

    print("-" * 96)
    print("结构合规  %s      内容命中  %s      预算合理  %s" % (
        summary["struct_ok"], summary["content_hit"], summary["budget_ok"]))
    print("judge均分 %.2f        平均耗时 %.1fs      降级 %d 例      天气命中 %d 例" % (
        summary["judge_avg"], summary["avg_elapsed"], summary["fallback_cases"], summary["weather_cases"]))
    print("跑偏（must_avoid 违规）%d 处" % summary["violations"])

    out = EVAL_DIR / ("result_e2e_%s.json" % version)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\n结果已存: %s" % out.name)


if __name__ == "__main__":
    main()
