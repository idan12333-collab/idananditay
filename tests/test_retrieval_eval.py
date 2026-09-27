"""Retrieval evaluation (evaluation/retrieval_eval.py): metrics, pooling, and local-only pages."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from evaluation import retrieval_eval as r


def test_rank_orders_by_similarity():
    vecs = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]])
    assert r.rank(np.array([0.0, 1.0]), ["a", "b", "c"], vecs) == ["b", "c", "a"]


def test_query_metrics():
    ranking = [f"h{i}" for i in range(60)]
    must = {"h0", "h5", "h30"}  # h30 is outside the top 20
    grades = {"h0": 3, "h1": 2, "h2": "hn", "h3": 0, "h4": 1}
    dup = {"h1": 9, "h4": 9}  # h4 duplicates the higher-ranked h1
    m = r.query_metrics(ranking, must, grades, dup, other_lang_ranking=ranking[10:30])
    assert m["must_recall@20"] == pytest.approx(2 / 3) and m["must_recall@50"] == 1.0
    assert m["p@10"] == pytest.approx(0.3)  # h0 (3), h1 (2), h5 (must, ungraded -> 3)
    assert m["hn@10"] == pytest.approx(0.1)
    assert m["dup@20"] == pytest.approx(1 / 20)
    assert m["he_en_overlap@20"] == pytest.approx(10 / 30)
    assert m["judged@10"] == pytest.approx(0.6)
    assert 0 < m["ndcg@20"] < 1


def test_query_metrics_perfect_and_empty():
    m = r.query_metrics(["a", "b"], {"a"}, {"b": 3}, {})
    assert m["ndcg@20"] == pytest.approx(1.0)
    m = r.query_metrics(["a"], set(), {}, {})
    assert m["must_recall@20"] is None and m["ndcg@20"] is None


def test_chosen_queries_and_held_out_are_deterministic():
    choice = {"queries": [{"id": "sea", "feasible": "yes"}, {"id": "cat", "feasible": "no"}, {"id": "pool", "feasible": "few"}],
              "extra": [{"he": "טיול לאילת", "en": "trip to Eilat"}]}
    qs = r.chosen_queries(choice)
    assert [q["id"] for q in qs] == ["sea", "pool", "x1"]
    assert qs[0]["en"] == "the sea" and qs[2]["he"] == "טיול לאילת"
    assert [q["held_out"] for q in qs] == [q["held_out"] for q in r.chosen_queries(choice)]
    assert sum(q["held_out"] for q in qs) == -(-len(qs) // 4)  # exactly ceil(25%)
    ids = [f"q{i}" for i in range(12)]
    assert len(r.held_out_ids(ids)) == 3 and r.held_out_ids(ids) == r.held_out_ids(list(reversed(ids)))


def test_pool_union_dedup_and_reuse_of_grades():
    qs = [{"id": "sea", "he": "ים", "hn": "בריכה"}]
    rankings = {("m1", "he", "sea"): ["a", "b", "c"], ("m2", "en", "sea"): ["c", "d"], ("m1", "he", "other"): ["z"]}
    items = r.pool_items(qs, rankings, {"sea": {"b": 2}})
    assert sorted(i["h"] for i in items) == ["a", "c", "d"]  # union, no duplicates, graded "b" not asked again
    assert items == r.pool_items(qs, rankings, {"sea": {"b": 2}})  # stable shuffle


def test_merge_grades(tmp_path: Path):
    (tmp_path / "1.json").write_text(json.dumps({"grades": {"sea": {"a": 3, "b": 0}}}), encoding="utf-8")
    (tmp_path / "2.json").write_text(json.dumps({"grades": {"sea": {"b": 2}, "pool": {"c": "hn"}}}), encoding="utf-8")
    assert r.merge_grades([tmp_path / "1.json", tmp_path / "2.json"]) == {"sea": {"a": 3, "b": 2}, "pool": {"c": "hn"}}


def test_pages_are_local_only(tmp_path: Path):
    thumb = {"h1": (tmp_path / "t1.jpg").as_uri()}
    cands = [{"id": "sea", "he": "ים", "en": "the sea", "hn": "בריכה"}]
    photos = [{"content_hash": "h1", "thumbnail_path": "t1.jpg", "capture_time": "2025-07-01T10:00:00"}]
    pages = [
        r.build_choose(15, cands, {"sea": ["h1"]}, thumb),
        r.build_mustfind(15, [{**cands[0], "held_out": False}], photos, tmp_path),
        r.build_pool(15, [{"q": "sea", "he": "ים", "hn": "בריכה", "h": "h1"}], thumb),
    ]
    for p in pages:
        assert "fetch(" not in p and "XMLHttpRequest" not in p and "http://" not in p and "https://" not in p
        assert "file:///" in p
    assert "2025-07" in pages[1]
