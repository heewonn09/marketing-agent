from utils import job_store


def test_schedule_crud(tmp_path):
    db = tmp_path / "jobs.db"
    job_store.init_db(db)
    sid = job_store.create_schedule(
        name="월요 발행", keywords=["AI 마케팅"], days="mon,thu", hour=9, minute=0,
        post_blog=True, post_instagram=False, enabled=True, db_path=db)
    assert isinstance(sid, int)

    s = job_store.get_schedule(sid, db_path=db)
    assert s["keywords"] == ["AI 마케팅"]
    assert s["days"] == "mon,thu" and s["hour"] == 9
    assert s["post_blog"] is True and s["post_instagram"] is False and s["enabled"] is True

    job_store.update_schedule(sid, db_path=db, hour=10, post_instagram=True, enabled=False)
    s = job_store.get_schedule(sid, db_path=db)
    assert s["hour"] == 10 and s["post_instagram"] is True and s["enabled"] is False

    assert len(job_store.list_schedules(db_path=db)) == 1
    job_store.delete_schedule(sid, db_path=db)
    assert job_store.get_schedule(sid, db_path=db) is None
    assert job_store.list_schedules(db_path=db) == []


def test_list_schedules_empty(tmp_path):
    db = tmp_path / "jobs.db"
    job_store.init_db(db)
    assert job_store.list_schedules(db_path=db) == []
