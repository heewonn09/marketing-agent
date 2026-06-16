"""스케줄 입력 검증 / 요일 정규화 / APScheduler cron kwargs (순수 함수)."""

_VALID_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def normalize_days(days) -> str:
    if days is None:
        raise ValueError("요일이 비어있습니다")
    if isinstance(days, str):
        items = [d.strip() for d in days.split(",") if d.strip()]
    else:
        items = [str(d).strip() for d in days if str(d).strip()]
    for d in items:
        if d not in _VALID_DAYS:
            raise ValueError(f"잘못된 요일: {d}")
    items_set = set(items)
    ordered = [d for d in _VALID_DAYS if d in items_set]
    if not ordered:
        raise ValueError("요일이 비어있습니다")
    return ",".join(ordered)


def cron_kwargs(days: str, hour: int, minute: int) -> dict:
    return {"day_of_week": days, "hour": int(hour), "minute": int(minute)}


def validate_schedule(payload: dict) -> tuple[bool, str]:
    kws = payload.get("keywords") or []
    if not isinstance(kws, list) or not [k for k in kws if str(k).strip()]:
        return False, "키워드를 1개 이상 입력하세요"
    try:
        normalize_days(payload.get("days"))
    except ValueError as e:
        return False, str(e)
    hour, minute = payload.get("hour"), payload.get("minute")
    if isinstance(hour, bool) or not isinstance(hour, int) or not (0 <= hour <= 23):
        return False, "시(hour)는 0~23"
    if isinstance(minute, bool) or not isinstance(minute, int) or not (0 <= minute <= 59):
        return False, "분(minute)은 0~59"
    if not (payload.get("post_blog") or payload.get("post_instagram")):
        return False, "발행 채널을 최소 1개 선택하세요"
    return True, ""
