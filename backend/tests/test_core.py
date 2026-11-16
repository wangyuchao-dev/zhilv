"""核心逻辑单元测试。

原则：不碰数据库、不碰 Redis、不调模型 —— 纯逻辑，秒级跑完。

跑法：
    cd backend
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from datetime import date

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.cache import _MemoryCache  # noqa: E402
from app.rag.retriever import RetrievalResult, RetrievedChunk, _city_filter  # noqa: E402
from app.schemas.plan import PlanRequest  # noqa: E402


def make_req(**overrides) -> PlanRequest:
    """造一份合法需求，测试里只改关心的字段。"""
    base = dict(
        user_name="测试用户",
        age=25,
        destination="大连",
        start_date=date(2026, 11, 15),
        end_date=date(2026, 11, 17),
        days=3,
        travelers=2,
        budget=3000,
        travel_style=["美食"],
    )
    base.update(overrides)
    return PlanRequest(**base)


class TestPlanRequest(unittest.TestCase):
    """表单校验。"""

    def test_cache_key_is_stable(self):
        """同样的表单必须算出同一个 key，否则缓存永远命中不了。"""
        self.assertEqual(make_req().cache_key(), make_req().cache_key())

    def test_cache_key_changes_with_input(self):
        """改任意一个字段，key 必须变，否则会串结果。"""
        self.assertNotEqual(make_req().cache_key(), make_req(travelers=3).cache_key())

    def test_days_auto_corrected_by_dates(self):
        """范围内天数与日期不符时，以日期为准。"""
        req = make_req(days=2)  # 日期算出来是 3 天
        self.assertEqual(req.days, 3)

    def test_days_over_limit_rejected(self):
        """超过 5 天直接拒绝，不会悄悄纠正 —— 之前的写法会让人以为填了 10 天。"""
        with self.assertRaises(Exception):
            make_req(days=10)

    def test_long_date_range_rejected_even_if_days_field_is_small(self):
        """回归：日期跨 17 天但 days 字段传 3，也不能靠 model_validator 绕过 le=5。"""
        with self.assertRaises(Exception):
            make_req(
                start_date=date(2026, 11, 12),
                end_date=date(2026, 11, 28),
                days=3,
            )

    def test_end_date_before_start_raises(self):
        with self.assertRaises(Exception):
            make_req(start_date=date(2026, 11, 17), end_date=date(2026, 11, 15))

    def test_unsupported_city_raises(self):
        """语料里只有 7 个城市，别的城市必须拦住。"""
        with self.assertRaises(Exception):
            make_req(destination="纽约")

    def test_empty_travel_style_raises(self):
        with self.assertRaises(Exception):
            make_req(travel_style=[])

    def test_travel_style_deduped(self):
        req = make_req(travel_style=["美食", "美食", "拍照"])
        self.assertEqual(req.travel_style, ["美食", "拍照"])

    def test_prompt_text_contains_key_info(self):
        """给模型的文本里必须带上城市、天数、人数，否则排出来的行程会跑偏。"""
        text = make_req().to_prompt_text()
        self.assertIn("大连", text)
        self.assertIn("3 天", text)
        self.assertIn("2 人", text)


class TestRetriever(unittest.TestCase):
    """检索层的纯逻辑。"""

    def test_city_filter_maps_to_file(self):
        self.assertEqual(_city_filter("大连"), {"source": "dalian_guide.md"})
        self.assertEqual(_city_filter("成都"), {"source": "chengdu_guide.md"})

    def test_city_filter_unknown_returns_none(self):
        self.assertIsNone(_city_filter("纽约"))

    def test_sources_dedup_by_title_and_source(self):
        """同一章节命中多次，sources 里只能出现一次。"""
        rr = RetrievalResult(
            chunks=[
                RetrievedChunk("核心景点", "dalian_guide.md", "文本一", 0.9),
                RetrievedChunk("核心景点", "dalian_guide.md", "文本二", 0.8),
                RetrievedChunk("住宿建议", "dalian_guide.md", "文本三", 0.7),
            ]
        )
        self.assertEqual(len(rr.as_sources()), 2)

    def test_empty_context_has_fallback_text(self):
        """检索为空时要给模型一句明确的话，而不是空字符串。"""
        self.assertIn("没有检索到", RetrievalResult().as_context())

    def test_context_numbered(self):
        """上下文必须带 [1] [2] 编号，模型才能标引用。"""
        rr = RetrievalResult(chunks=[RetrievedChunk("景点", "a.md", "内容", 0.9)])
        self.assertIn("[1]", rr.as_context())


class TestMemoryCache(unittest.TestCase):
    """Redis 不可用时的降级实现。"""

    def test_set_and_get(self):
        c = _MemoryCache()
        c.set("k", {"v": 1}, ttl=30)
        self.assertEqual(c.get("k"), {"v": 1})

    def test_ttl_expires(self):
        c = _MemoryCache()
        c.set("k", "v", ttl=0.05)
        self.assertEqual(c.get("k"), "v")
        time.sleep(0.12)
        self.assertIsNone(c.get("k"))

    def test_incr_starts_at_one_and_counts(self):
        """限流靠它，第一次必须是 1 而不是 0。"""
        c = _MemoryCache()
        self.assertEqual(c.incr("rate", 60), 1)
        self.assertEqual(c.incr("rate", 60), 2)
        self.assertEqual(c.incr("rate", 60), 3)

    def test_delete(self):
        c = _MemoryCache()
        c.set("k", "v", ttl=30)
        c.delete("k")
        self.assertIsNone(c.get("k"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
