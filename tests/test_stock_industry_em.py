from fund_platform.stock_industry_em import _industry_from_em_payload, normalize_em_industry


def test_industry_from_em_payload_reads_f127():
    payload = {"data": {"f57": "600519", "f58": "贵州茅台", "f127": "白酒Ⅱ"}}
    assert _industry_from_em_payload(payload) == "白酒Ⅱ"


def test_normalize_em_industry_strips_suffix_and_matches_known():
    known = {"白酒", "银行"}
    assert normalize_em_industry("白酒Ⅱ", known) == "白酒"
