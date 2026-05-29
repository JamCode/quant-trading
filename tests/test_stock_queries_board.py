"""Unit tests for A-share board filter helpers."""

from __future__ import annotations

from fund_platform import stock_queries


def test_normalize_stock_board():
    assert stock_queries.normalize_stock_board("sh") == "sh"
    assert stock_queries.normalize_stock_board("KCB") == "kcb"
    assert stock_queries.normalize_stock_board("invalid") is None
    assert stock_queries.normalize_stock_board("") is None


def test_board_filter_sql_fragments():
    assert "688%%" in stock_queries.board_filter_sql("kcb")
    assert "30%%" in stock_queries.board_filter_sql("cyb")
    assert stock_queries.board_filter_sql("nope") == ""


def test_board_filter_sql_bj_includes_92_prefix():
    sql = stock_queries.board_filter_sql("bj")
    assert "92%%" in sql
