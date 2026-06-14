from utils.checkpoint import clear, load_completed, mark_completed


def test_load_completed_empty_when_missing(tmp_path):
    assert load_completed(tmp_path / "none.json") == set()


def test_mark_and_load(tmp_path):
    path = tmp_path / "cp.json"
    mark_completed(path, "collector")
    mark_completed(path, "analyzer")
    assert load_completed(path) == {"collector", "analyzer"}


def test_mark_is_idempotent(tmp_path):
    path = tmp_path / "cp.json"
    mark_completed(path, "collector")
    mark_completed(path, "collector")
    assert load_completed(path) == {"collector"}


def test_clear_removes_file(tmp_path):
    path = tmp_path / "cp.json"
    mark_completed(path, "x")
    clear(path)
    assert not path.exists()
    assert load_completed(path) == set()


def test_load_corrupt_returns_empty(tmp_path):
    path = tmp_path / "cp.json"
    path.write_text("not json{{", encoding="utf-8")
    assert load_completed(path) == set()
