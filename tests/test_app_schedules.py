# tests/test_app_schedules.py
import os, queue, time
os.environ["DISABLE_SCHEDULER"] = "1"   # import 시 스케줄러 미기동
import app as a


def _job(jid, kws):
    a.jobs[jid] = {"status": "running", "queue": queue.Queue(), "date": None,
                   "keywords": kws, "last_step": None, "started_at": time.time(),
                   "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None}


def test_part2_blog_only(monkeypatch):
    ran = []
    monkeypatch.setattr(a, "_run_cmd",
        lambda jid, name, script, args, fatal=True: ran.append(script) or True)
    monkeypatch.setattr(a, "notify_done", lambda *x, **k: None)
    monkeypatch.setattr(a, "upsert_job", lambda *x, **k: None)
    _job("j1", ["k"])
    a._run_pipeline_part2("j1", ["k"], "2026-06-16", post_blog=True, post_instagram=False)
    assert any("poster" in s for s in ran)
    assert not any("instagram" in s for s in ran)


def test_part2_ig_only(monkeypatch):
    ran = []
    monkeypatch.setattr(a, "_run_cmd",
        lambda jid, name, script, args, fatal=True: ran.append(script) or True)
    monkeypatch.setattr(a, "notify_done", lambda *x, **k: None)
    monkeypatch.setattr(a, "upsert_job", lambda *x, **k: None)
    _job("j2", ["k"])
    a._run_pipeline_part2("j2", ["k"], "2026-06-16", post_blog=False, post_instagram=True)
    assert any("instagram" in s for s in ran)
    assert not any("poster" in s for s in ran)
