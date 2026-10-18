"""Сборка приложения из конфигурации, замена источника в тесте и сквозной сценарий."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from school_lab.adapters.declaration import DeclarationAnalyzer
from school_lab.adapters.sources import InMemorySource, JSONLSource, load_assignments
from school_lab.app import BUILTIN_ANALYZERS, AppConfig, build_application
from school_lab.cli import main
from school_lab.domain.analysis import validate_report
from school_lab.domain.errors import SubmissionError
from school_lab.domain.validation import parse_assignments
from school_lab.services.ports import SubmissionSource

from conftest import DATA_DIR, RAW_EXAMPLE, changed, load_public_submissions

ASSIGNMENTS = load_assignments(DATA_DIR / "assignments.json")


# --- замена реального источника in-memory реализацией --------------------------------

def test_real_source_is_replaced_by_in_memory_in_test() -> None:
    """Сервис приёма не знает, откуда пришли записи: JSONL в проде, список в тесте."""
    app = build_application(ASSIGNMENTS)
    fake: SubmissionSource = InMemorySource([RAW_EXAMPLE, changed(student_id=""), RAW_EXAMPLE])
    summary = app.import_from(fake)
    assert summary.accepted == ["sub-001"]
    assert summary.duplicate == ["sub-001"]
    assert [(e["line_no"], e["field"]) for e in summary.errors] == [(2, "student_id")]
    assert app.analyze("sub-001", "length").findings


def test_jsonl_and_in_memory_give_same_result() -> None:
    from_file = build_application(ASSIGNMENTS).import_from(JSONLSource(DATA_DIR / "submissions.jsonl"))
    from_memory = build_application(ASSIGNMENTS).import_from(InMemorySource(load_public_submissions()))
    assert from_file == from_memory


# --- конфигурация и отсутствие глобального состояния ---------------------------------

def test_each_application_is_independent() -> None:
    first, second = build_application(ASSIGNMENTS), build_application(ASSIGNMENTS)
    first.import_from(InMemorySource([RAW_EXAMPLE]))
    assert len(first.repository) == 1
    assert len(second.repository) == 0
    assert first.registry is not second.registry
    with pytest.raises(TypeError):  # встроенная таблица анализаторов неизменяема
        BUILTIN_ANALYZERS["hack"] = DeclarationAnalyzer  # type: ignore[index]


def test_api_and_import_share_one_service() -> None:
    app = build_application(ASSIGNMENTS)
    assert app.api.post_submission(json.dumps(RAW_EXAMPLE)).status == 201
    summary = app.import_from(InMemorySource([RAW_EXAMPLE]))
    assert summary.duplicate == ["sub-001"]


def test_config_values_reach_report_config_hash() -> None:
    base = build_application(ASSIGNMENTS)
    other = build_application(ASSIGNMENTS, config=AppConfig(config_version="2"))
    for app in (base, other):
        app.import_from(InMemorySource([RAW_EXAMPLE]))
    assert base.analyze("sub-001", "length").config_hash != other.analyze("sub-001", "length").config_hash


def test_third_analyzer_is_connected_by_config_only() -> None:
    """Защита: третий анализатор подключается конфигурацией, AnalysisService не меняется."""
    plain = build_application(ASSIGNMENTS)
    assert plain.registry.names() == ("length", "template")
    app = build_application(ASSIGNMENTS, extra_analyzers={"declaration": DeclarationAnalyzer})
    assert app.registry.names() == ("length", "template", "declaration")
    app.import_from(InMemorySource(load_public_submissions()))
    no_ai = app.analyze("sub-001", "declaration")
    with_ai = app.analyze("sub-003", "declaration")
    assert "не заявлено" in no_ai.findings[0].explanation
    assert "учебный помощник" in with_ai.findings[0].explanation
    assert with_ai.review_required is False  # verified_by_student = true


def test_declaration_analyzer_flags_unverified_use() -> None:
    app = build_application(ASSIGNMENTS, extra_analyzers={"declaration": DeclarationAnalyzer})
    declaration = {"used": True, "tool": "ассистент", "purpose": "отладка", "verified_by_student": False}
    app.import_from(InMemorySource([changed(ai_declaration=declaration)]))
    report = app.analyze("sub-001", "declaration")
    assert report.review_required is True
    assert "ручная проверка" in report.findings[0].explanation


# --- сквозной сценарий --------------------------------------------------------------------

def test_end_to_end() -> None:
    app = build_application(ASSIGNMENTS)
    first = app.import_from(JSONLSource(DATA_DIR / "submissions.jsonl"))
    second = app.import_from(InMemorySource(load_public_submissions()))
    assert len(first.accepted) == 12 and not first.errors
    assert len(second.duplicate) == 12 and not second.accepted and not second.errors

    reports = 0
    for submission_id in first.accepted:
        original = app.repository.get(submission_id)
        assert original is not None
        snapshot = asdict(original)
        for name in ("length", "template"):
            report = app.analyze(submission_id, name)
            validate_report(report, original, app.context_for(submission_id))
            reports += 1
        assert asdict(app.repository.get(submission_id)) == snapshot  # type: ignore[arg-type]
    assert reports == 24


def test_assignments_file_is_validated() -> None:
    with pytest.raises(SubmissionError):
        parse_assignments({"assignment_id": "a"})
    with pytest.raises(SubmissionError) as caught:
        parse_assignments([
            {"assignment_id": "a", "title": "t", "allowed_template": "", "requirements": []},
            {"assignment_id": "a", "title": "t", "allowed_template": "", "requirements": []},
        ])
    assert caught.value.code == "conflict"


# --- CLI analyze --------------------------------------------------------------------------

def test_cli_analyze(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", str(data_dir / "submissions.jsonl"), "--assignments", str(data_dir / "assignments.json")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(payload["reports"]) == 24
    assert payload["analysis_errors"] == []
    assert {r["analyzer_id"] for r in payload["reports"]} == {"length", "template"}


def test_cli_analyze_unknown_analyzer_is_reported(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([
        "analyze", str(data_dir / "submissions.jsonl"),
        "--assignments", str(data_dir / "assignments.json"), "--analyzer", "nope",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["reports"] == []
    assert all("Неизвестный анализатор" in e["message"] for e in payload["analysis_errors"])


def test_cli_analyze_bad_assignments(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "assignments.json"
    bad.write_text("{broken", encoding="utf-8")
    code = main(["analyze", str(data_dir / "submissions.jsonl"), "--assignments", str(bad)])
    assert code == 2
    assert json.loads(capsys.readouterr().err)["code"] == "invalid_assignments"
