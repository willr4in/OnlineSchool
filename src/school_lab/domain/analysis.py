"""Контракт анализатора, контекст анализа и проверка отчёта на границе."""

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from school_lab.domain.errors import AnalysisFailure
from school_lab.domain.hashing import stable_hash, submission_hash
from school_lab.domain.models import AnalysisReport, Assignment, Finding, Submission

FINDING_KINDS = frozenset({"similarity", "rubric_feedback", "processing_error"})
EVIDENCE_FIELDS = frozenset({"text", "code"})


class SubmissionLookup(Protocol):
    """Доступ анализатора к другим принятым сдачам (только чтение)."""

    def get(self, submission_id: str) -> Submission | None: ...


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    assignment: Assignment
    mode: Literal["baseline", "stub"] = "baseline"
    config_version: str = "1"
    # Доступ к данным через интерфейс; в config_hash не входит.
    submissions: SubmissionLookup | None = None

    def config_payload(self) -> dict[str, object]:
        return {"assignment": asdict(self.assignment), "mode": self.mode, "config_version": self.config_version}

    @property
    def config_hash(self) -> str:
        return stable_hash(self.config_payload())


class Analyzer(Protocol):
    @property
    def analyzer_id(self) -> str: ...

    @property
    def analyzer_version(self) -> str: ...

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport: ...


Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_report_id() -> str:
    return str(uuid4())


def make_report(
    submission: Submission,
    context: AnalysisContext,
    analyzer_id: str,
    analyzer_version: str,
    findings: tuple[Finding, ...],
    *,
    review_required: bool = False,
    clock: Clock = utc_now,
    id_factory: IdFactory = new_report_id,
) -> AnalysisReport:
    report = AnalysisReport(
        report_id=id_factory(),
        submission_id=submission.submission_id,
        submission_hash=submission_hash(submission),
        analyzer_id=analyzer_id,
        analyzer_version=analyzer_version,
        config_hash=context.config_hash,
        findings=findings,
        created_at=clock().isoformat(),
        review_required=review_required,
    )
    validate_report(report, submission, context)
    return report


def validate_report(report: object, submission: Submission, context: AnalysisContext) -> None:
    """Аннотация -> AnalysisReport не заставляет анализатор вернуть корректный объект: проверяем явно."""
    if not isinstance(report, AnalysisReport):
        raise AnalysisFailure("Ожидается AnalysisReport")
    if report.submission_id != submission.submission_id or report.submission_hash != submission_hash(submission):
        raise AnalysisFailure("Отчёт ссылается на другую версию сдачи")
    if report.config_hash != context.config_hash:
        raise AnalysisFailure("Отчёт использует другую конфигурацию")
    for name in ("report_id", "analyzer_id", "analyzer_version"):
        value = getattr(report, name)
        if not isinstance(value, str) or not value.strip():
            raise AnalysisFailure(f"Поле {name} должно быть непустой строкой")
    if type(report.review_required) is not bool:
        raise AnalysisFailure("review_required должен быть bool")
    try:
        created = datetime.fromisoformat(report.created_at)
    except (TypeError, ValueError) as exc:
        raise AnalysisFailure("Время отчёта имеет неверный формат") from exc
    if created.tzinfo is None or created.utcoffset() is None:
        raise AnalysisFailure("Часовой пояс времени отчёта обязателен")
    if not isinstance(report.findings, tuple):
        raise AnalysisFailure("findings должен быть кортежем")
    for finding in report.findings:
        _validate_finding(finding, submission)


def _validate_finding(finding: object, submission: Submission) -> None:
    if not isinstance(finding, Finding):
        raise AnalysisFailure("Ожидается Finding")
    if finding.kind not in FINDING_KINDS:
        raise AnalysisFailure(f"Неизвестный kind: {finding.kind!r}")
    score: object = finding.score
    if score is not None:
        # bool — подкласс int, поэтому True отдельно исключается из числовых оценок.
        if (
            isinstance(score, bool)
            or not isinstance(score, int | float)
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise AnalysisFailure("score должен быть конечным числом 0–1 либо None")
    if not isinstance(finding.explanation, str) or not finding.explanation.strip():
        raise AnalysisFailure("Объяснение наблюдения обязательно")
    for evidence in finding.evidence:
        if evidence.submission_id != submission.submission_id or evidence.field not in EVIDENCE_FIELDS:
            raise AnalysisFailure("Evidence ссылается на неизвестную сдачу или поле")
        if type(evidence.start_line) is not int or type(evidence.end_line) is not int:
            raise AnalysisFailure("Номер строки evidence должен быть int")
        line_count = len(getattr(submission, evidence.field).splitlines())
        if not 1 <= evidence.start_line <= evidence.end_line <= line_count:
            raise AnalysisFailure(
                f"Evidence {evidence.field}:{evidence.start_line}-{evidence.end_line} "
                f"выходит за границы исходного текста (строк: {line_count})"
            )
