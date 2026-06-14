import json

import pytest

from agents.reporter import main as reporter


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter, "OUTPUT_DIR", tmp_path)
    (tmp_path / "content_AI_2026-06-08.json").write_text(
        json.dumps({"k": "AI"}), encoding="utf-8"
    )
    (tmp_path / "content_B_2026-06-08.json").write_text(
        json.dumps({"k": "B"}), encoding="utf-8"
    )
    return tmp_path


def test_load_content_files_all_keywords(output_dir):
    items, files = reporter.load_content_files("2026-06-08")
    assert len(items) == 2
    assert len(files) == 2


def test_load_content_files_filtered_by_keyword(output_dir):
    items, files = reporter.load_content_files("2026-06-08", keyword="AI")
    assert len(items) == 1
    assert items[0]["k"] == "AI"


def test_load_content_files_none_for_other_date(output_dir):
    items, files = reporter.load_content_files("2099-01-01")
    assert items == []
    assert files == []
