import json
from pathlib import Path

import pytest

from school_lab.cli import main


def run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_import_valid_file(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run_cli(["import", str(data_dir / "submissions.jsonl")], capsys)
    report = json.loads(out)
    assert code == 0
    assert err == ""
    assert len(report["accepted"]) == 12
    assert report["duplicate"] == []
    assert report["errors"] == []


def test_import_invalid_file_reports_line_numbers(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run_cli(["import", str(data_dir / "invalid_submissions.jsonl")], capsys)
    report = json.loads(out)
    assert code == 1
    assert report["accepted"] == ["sub-101", "sub-102"]
    assert report["duplicate"] == ["sub-101"]
    errors = {e["line_no"]: (e["code"], e["field"]) for e in report["errors"]}
    assert errors == {
        2: ("invalid_json", "json"),
        4: ("conflict", "submission_id"),
        5: ("schema_error", "student_id"),
        6: ("schema_error", "submitted_at"),
        7: ("schema_error", "submitted_at"),
        8: ("schema_error", "studnet_id"),
        9: ("schema_error", "schema_version"),
        10: ("unsupported_version", "schema_version"),
        11: ("schema_error", "ai_declaration"),
        12: ("schema_error", "ai_declaration.used"),
        13: ("schema_error", "code"),
        14: ("schema_error", "text/code"),
        15: ("invalid_json", "json"),
        16: ("schema_error", "submission"),
        17: ("invalid_json", "submission_id"),
        18: ("invalid_json", "json"),
        19: ("schema_error", "template_id"),
        20: ("schema_error", "ai_declaration.verified_by_student"),
    }


def test_missing_file_is_source_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run_cli(["import", str(tmp_path / "nope.jsonl")], capsys)
    assert code == 2
    assert out == ""
    assert json.loads(err)["code"] == "source_unavailable"
