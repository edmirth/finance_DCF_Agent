from datetime import datetime, timedelta

from backend.stock_chart_router import filter_chart_data_by_period


def test_filter_chart_data_by_period_accepts_fmp_historical_wrapper():
    recent_date = datetime.now().date().isoformat()
    old_date = (datetime.now() - timedelta(days=90)).date().isoformat()

    data = {
        "historical": [
            {"date": recent_date, "close": 101},
            {"date": old_date, "close": 91},
        ]
    }

    assert filter_chart_data_by_period(data, "1M") == [{"date": recent_date, "close": 101}]


def test_filter_chart_data_by_period_handles_intraday_list():
    rows = [{"date": "2026-05-22 10:00:00", "close": 200}]

    assert filter_chart_data_by_period(rows, "1D") == rows


def test_filter_chart_data_by_period_rejects_malformed_data():
    assert filter_chart_data_by_period({"unexpected": "shape"}, "1M") == []
