# tests/test_schedule_util.py
import pytest
from utils.schedule_util import normalize_days, cron_kwargs, validate_schedule


def test_normalize_days_from_list():
    assert normalize_days(["mon", "thu"]) == "mon,thu"

def test_normalize_days_from_csv_and_dedup_order():
    assert normalize_days("thu, mon, mon") == "mon,thu"

def test_normalize_days_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_days(["funday"])

def test_cron_kwargs():
    assert cron_kwargs("mon,thu", 9, 0) == {"day_of_week": "mon,thu", "hour": 9, "minute": 0}

def test_validate_ok():
    ok, err = validate_schedule({"keywords": ["AI 마케팅"], "days": ["mon"],
                                 "hour": 9, "minute": 0, "post_blog": True, "post_instagram": False})
    assert ok and err == ""

def test_validate_empty_keywords():
    ok, err = validate_schedule({"keywords": [], "days": ["mon"], "hour": 9, "minute": 0,
                                 "post_blog": True, "post_instagram": True})
    assert not ok and "키워드" in err

def test_validate_bad_hour():
    ok, err = validate_schedule({"keywords": ["x"], "days": ["mon"], "hour": 24, "minute": 0,
                                 "post_blog": True, "post_instagram": True})
    assert not ok

def test_validate_no_channel():
    ok, err = validate_schedule({"keywords": ["x"], "days": ["mon"], "hour": 9, "minute": 0,
                                 "post_blog": False, "post_instagram": False})
    assert not ok and "채널" in err
