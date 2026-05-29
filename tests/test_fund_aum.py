from fund_platform.fund_aum import aum_from_basic_map, parse_aum_to_yi


def test_parse_aum_yi():
    assert parse_aum_to_yi("34.49亿") == 34.49
    assert parse_aum_to_yi("15.12亿元") == 15.12
    assert parse_aum_to_yi("5000万") == 0.5


def test_aum_from_basic_map():
    yi, label = aum_from_basic_map({"最新规模": "34.49亿"})
    assert yi == 34.49
    assert label == "34.49亿"
