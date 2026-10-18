"""Контрактные тесты анализаторов + проверки семантики LengthAnalyzer и TemplateAnalyzer."""

import copy
import math
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from school_lab.adapters.analyzers import LengthAnalyzer, TemplateAnalyzer, nonempty_line_numbers, template_ranges
from school_lab.domain.analysis import AnalysisContext, Analyzer, make_report, validate_report
from school_lab.domain.errors import AnalysisFailure
from school_lab.domain.models import AnalysisReport, Assignment, Evidence, Finding, Submission
from school_lab.domain.validation import parse_submission

from conftest import RAW_EXAMPLE, changed, load_public_submissions

ASSIGNMENT = Assignment("assignment-01", "Сумма квадратов", "from typing import Iterable\n", ("Функция solve",))
CONTEXT = AnalysisContext(ASSIGNMENT)
PUBLIC = [parse_submission(raw) for raw in load_public_submissions()]

ANALYZERS: list[type[LengthAnalyzer] | type[TemplateAnalyzer]] = [LengthAnalyzer, TemplateAnalyzer]


# --- общий контракт ------------------------------------------------------------------

@pytest.mark.parametrize("analyzer_cls", ANALYZERS, ids=lambda c: c.analyzer_id)
@pytest.mark.parametrize("submission", PUBLIC, ids=lambda s: s.submission_id)
def test_analyzer_contract(analyzer_cls: type[Analyzer], submission: Submission) -> None:
    analyzer: Analyzer = analyzer_cls()
    snapshot = asdict(submission)
    first = analyzer.analyze(submission, CONTEXT)
    second = analyzer.analyze(submission, CONTEXT)

    for report in (first, second):
        validate_report(report, submission, CONTEXT)  # связь со сдачей, конфиг, диапазоны evidence
        assert report.analyzer_id == analyzer.analyzer_id
        assert report.analyzer_version == analyzer.analyzer_version
        assert report.findings and all(f.explanation.strip() for f in report.findings)
    # Повторяемость смысла, но не идентификатора запуска.
    assert first.findings == second.findings
    assert first.report_id != second.report_id
    assert asdict(submission) == snapshot  # исходный объект не изменился


def test_injected_clock_and_ids_make_report_reproducible() -> None:
    fixed = datetime(2026, 9, 1, tzinfo=UTC)

    def build() -> AnalysisReport:
        finding = Finding("rubric_feedback", None, (), "x")
        return make_report(PUBLIC[0], CONTEXT, "a", "1", (finding,), clock=lambda: fixed, id_factory=lambda: "r-1")

    assert build() == build()


# --- LengthAnalyzer -----------------------------------------------------------------

def test_nonempty_lines_use_original_numbering() -> None:
    assert nonempty_line_numbers("\n a \n\n b\n") == (2, 4)
    assert nonempty_line_numbers("") == ()


def test_length_analyzer_counts_and_has_no_score() -> None:
    report = LengthAnalyzer().analyze(PUBLIC[0], CONTEXT)
    (finding,) = report.findings
    assert finding.kind == "rubric_feedback"
    assert finding.score is None
    assert "text=1, code=3" in finding.explanation
    code_lines = [e.start_line for e in finding.evidence if e.field == "code"]
    assert code_lines == [1, 3, 4]  # строка 2 пустая и в evidence не попадает


# --- TemplateAnalyzer (упражнение 4) ------------------------------------------------

TWO_LINE_TEMPLATE = "import math\nfrom typing import Iterable\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("import math\nfrom typing import Iterable\nx = 1\n", ((1, 2),), id="exact"),
        pytest.param("import math\nfrom typing  import Iterable\n", (), id="whitespace-changed"),
        pytest.param("# c\nimport math\nfrom typing import Iterable\n", ((2, 3),), id="offset"),
        pytest.param(
            "import math\nfrom typing import Iterable\n\nimport math\nfrom typing import Iterable",
            ((1, 2), (4, 5)),
            id="two-matches",
        ),
        pytest.param("print(1)\n", (), id="no-match"),
    ],
)
def test_template_ranges(source: str, expected: tuple[tuple[int, int], ...]) -> None:
    assert template_ranges(source, TWO_LINE_TEMPLATE) == expected


def test_blank_template_matches_nothing() -> None:
    assert template_ranges("a\n\n", " \n") == ()
    assert template_ranges("a\n", "") == ()


def test_template_analyzer_reports_allowed_match() -> None:
    sub_007 = next(s for s in PUBLIC if s.submission_id == "sub-007")
    report = TemplateAnalyzer().analyze(sub_007, CONTEXT)
    (finding,) = report.findings
    assert finding.kind == "similarity"
    assert finding.score is None
    assert [(e.start_line, e.end_line) for e in finding.evidence] == [(1, 1)]
    assert "разрешено" in finding.explanation


def test_template_analyzer_without_match() -> None:
    sub_008 = next(s for s in PUBLIC if s.submission_id == "sub-008")
    (finding,) = TemplateAnalyzer().analyze(sub_008, CONTEXT).findings
    assert finding.evidence == ()
    assert "не найдено" in finding.explanation


def test_template_analyzer_rejects_other_assignment() -> None:
    other = AnalysisContext(Assignment("assignment-02", "Другое", "x\n", ()))
    with pytest.raises(AnalysisFailure):
        TemplateAnalyzer().analyze(PUBLIC[0], other)


# --- проверка отчёта на границе (упражнение 6) --------------------------------------

def _good_report() -> tuple[AnalysisReport, Submission]:
    submission = parse_submission(copy.deepcopy(RAW_EXAMPLE))
    return LengthAnalyzer().analyze(submission, CONTEXT), submission


def _with_finding(report: AnalysisReport, **updates: object) -> AnalysisReport:
    return replace(report, findings=(replace(report.findings[0], **updates),))  # type: ignore[arg-type]


def _with_evidence(report: AnalysisReport, **updates: object) -> AnalysisReport:
    evidence = replace(report.findings[0].evidence[0], **updates)  # type: ignore[arg-type]
    return _with_finding(report, evidence=(evidence,))


BAD_REPORTS = {
    "score-true": lambda r: _with_finding(r, score=True),
    "score-nan": lambda r: _with_finding(r, score=math.nan),
    "score-1.5": lambda r: _with_finding(r, score=1.5),
    "score-negative": lambda r: _with_finding(r, score=-0.1),
    "empty-explanation": lambda r: _with_finding(r, explanation="  "),
    "unknown-kind": lambda r: _with_finding(r, kind="verdict"),
    "line-zero": lambda r: _with_evidence(r, start_line=0),
    "end-beyond-source": lambda r: _with_evidence(r, end_line=99),
    "start-after-end": lambda r: _with_evidence(r, start_line=2, end_line=1),
    "unknown-field": lambda r: _with_evidence(r, field="title"),
    "other-submission": lambda r: _with_evidence(r, submission_id="sub-999"),
    "line-as-str": lambda r: _with_evidence(r, start_line="1"),
    "wrong-hash": lambda r: replace(r, submission_hash="incorrect"),
    "wrong-config": lambda r: replace(r, config_hash="other"),
    "naive-created-at": lambda r: replace(r, created_at="2026-09-01T10:00:00"),
    "empty-analyzer-id": lambda r: replace(r, analyzer_id=""),
    "review-required-int": lambda r: replace(r, review_required=1),
    "not-a-report": lambda r: asdict(r),
}


@pytest.mark.parametrize("mutate", BAD_REPORTS.values(), ids=BAD_REPORTS.keys())
def test_validate_report_rejects(mutate: object) -> None:
    report, submission = _good_report()
    with pytest.raises(AnalysisFailure):
        validate_report(mutate(report), submission, CONTEXT)  # type: ignore[operator]


def test_valid_score_bounds_are_accepted() -> None:
    report, submission = _good_report()
    for score in (0, 0.5, 1.0):
        validate_report(_with_finding(report, score=score), submission, CONTEXT)


def test_evidence_for_last_line_without_trailing_newline() -> None:
    submission = parse_submission(changed(code="a\nb"))
    evidence = (Evidence(submission.submission_id, "code", 2, 2),)
    report = make_report(submission, CONTEXT, "x", "1", (Finding("similarity", None, evidence, "ok"),))
    assert report.findings[0].evidence[0].end_line == 2


def test_config_hash_changes_with_config() -> None:
    # Упражнение 7: другой шаблон или версия конфигурации — это другая конфигурация.
    assert replace(CONTEXT, config_version="2").config_hash != CONTEXT.config_hash
    other_template = AnalysisContext(replace(ASSIGNMENT, allowed_template="import os\n"))
    assert other_template.config_hash != CONTEXT.config_hash
    old_report = LengthAnalyzer().analyze(PUBLIC[0], CONTEXT)
    with pytest.raises(AnalysisFailure, match="конфигурац"):
        validate_report(old_report, PUBLIC[0], other_template)
