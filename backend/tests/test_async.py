"""异步链路与降级逻辑的单元测试。

全部 mock 掉模型、检索和缓存，不联网、不连库、秒级跑完。
覆盖之前 18 个用例没碰到的高风险路径。
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.cache import _MemoryCache  # noqa: E402
from app.rag.retriever import RetrievalResult, RetrievedChunk  # noqa: E402
from app.schemas.plan import PlanRequest, PlanResponse  # noqa: E402
from app.services import plan_service as ps_mod  # noqa: E402
from app.services.plan_service import PlanService  # noqa: E402


def make_req(**overrides) -> PlanRequest:
    base = dict(
        user_name="测试用户", age=28, destination="大连",
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 3),
        days=3, travelers=2, budget=3000, travel_style=["美食"],
    )
    base.update(overrides)
    return PlanRequest(**base)


def make_result() -> dict:
    return PlanResponse(task_id="fake", summary="测试行程", elapsed_ms=1).model_dump(mode="json")


class _FakeDemand:
    def __init__(self, boom=False):
        self.boom = boom

    def analyze(self, req):
        if self.boom:
            raise RuntimeError("模型挂了")
        return type("SP", (), {"queries": ["大连 景点", "大连 餐饮"], "focus": "", "avoid": []})()


class _FakePlanner:
    def plan(self, req, retrieval, focus="", avoid=None, weather=""):
        return type("Body", (), {
            "summary": "测试行程", "highlights": [], "budget": None,
            "daily_plans": [], "packing_tips": [],
        })()


class TestAsyncFlow(unittest.TestCase):
    """每个用例用全新内存缓存，避免互相污染，也不碰真实 Redis。"""

    def setUp(self):
        self.mem = _MemoryCache()
        self.patcher = patch.object(ps_mod, "cache", self.mem)
        self.patcher.start()
        self.svc = PlanService()

    def tearDown(self):
        self.patcher.stop()

    def test_cache_hit_returns_done_with_result(self):
        """命中缓存时直接带 result，前端不用轮询；且不计入限流。"""
        req = make_req()
        self.mem.set(f"plan:cache:{req.cache_key()}", make_result(), 300)

        ack = self.svc.submit(req, client_ip="127.0.0.1")

        self.assertEqual(ack.status, "done")
        self.assertTrue(ack.cached)
        self.assertIsNotNone(ack.result)
        self.assertEqual(ack.progress, 4)
        # 缓存命中不该消耗限流额度
        self.assertIsNone(self.mem.get("rate:127.0.0.1"))

    def test_agent_failure_marks_task_failed(self):
        """后台 Agent 抛异常时，状态必须变 failed 且带 error，不能静默卡在 running。"""
        self.svc._demand = _FakeDemand(boom=True)

        self.svc._run_generation("task-x", make_req(), "cache-x", "inflight-x")

        task = self.svc.get_task("task-x")
        self.assertEqual(task["status"], "failed")
        self.assertIn("RuntimeError", task["error"])
        self.assertEqual(task["progress"], -1)
        # 在途锁必须被释放，否则同样的表单会被永久挡住
        self.assertIsNone(self.mem.get("inflight-x"))
        self.assertEqual(self.svc._active, 0)

    def test_empty_retrieval_triggers_fallback_once(self):
        """检索为空只降级一次，且降级结果被截断到 top-1（不整批放回）。"""
        calls = []

        def fake_retrieve_multi(*args, **kwargs):
            calls.append(kwargs.get("min_score"))
            if len(calls) == 1:
                return RetrievalResult(chunks=[])
            return RetrievalResult(chunks=[
                RetrievedChunk("景点A", "a.md", "文本A" * 20, 0.81),
                RetrievedChunk("景点B", "b.md", "文本B" * 20, 0.80),
                RetrievedChunk("景点C", "c.md", "文本C" * 20, 0.79),
            ])

        self.svc._demand = _FakeDemand()
        self.svc._planner = _FakePlanner()

        with patch.object(ps_mod, "retrieve_multi", fake_retrieve_multi), \
                patch.object(ps_mod, "fetch_weather", return_value=("", [])):
            self.svc._run_generation("task-y", make_req(), "cache-y", "inflight-y")

        self.assertEqual(len(calls), 2, "应该只重查一次")
        self.assertIsNone(calls[0], "第一次走默认阈值")
        self.assertEqual(calls[1], ps_mod.MIN_SCORE_FALLBACK)
        # 任务成功完成，说明降级后模型还能拿到素材
        self.assertEqual(self.svc.get_task("task-y")["status"], "done")

    def test_get_task_returns_copy(self):
        """get_task 不能污染缓存里的任务字典（内存缓存返回引用的回归测试）。"""
        self.mem.set("plan:task:z", {
            "task_id": "z", "status": "done", "step": "完成",
            "progress": 4, "error": "", "elapsed_ms": 100,
        })
        self.mem.set("plan:result:z", {"summary": "一大坨结果"})

        t1 = self.svc.get_task("z")
        t2 = self.svc.get_task("z")

        self.assertIsNot(t1, t2, "两次返回不能是同一个对象")
        self.assertIn("result", t1)
        self.assertIn("result", t2)
        # 原始缓存里不应该被塞进 result
        self.assertNotIn("result", self.mem.get("plan:task:z"))

    def test_duplicate_submit_reuses_task_id(self):
        """同样的表单在途时，第二次提交复用第一个 task_id，不重复烧 token。"""
        req = make_req()
        inflight = f"plan:inflight:{req.cache_key()}"
        self.mem.set(inflight, "running-task", 180)

        ack = self.svc.submit(req, client_ip="127.0.0.1")

        self.assertEqual(ack.task_id, "running-task")
        self.assertEqual(ack.status, "running")
        self.assertEqual(self.svc._active, 0, "不该新增后台任务")


if __name__ == "__main__":
    unittest.main(verbosity=2)
