"""Доменные модели."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class AIDeclaration:
    used: bool
    tool: str | None
    purpose: str | None
    verified_by_student: bool


@dataclass(frozen=True, slots=True)
class Submission:
    schema_version: int
    submission_id: str
    student_id: str
    assignment_id: str
    submitted_at: str  # Оригинальное представление из JSON: от него зависит хеш.
    text: str
    code: str
    template_id: str | None
    ai_declaration: AIDeclaration


@dataclass(frozen=True, slots=True)
class Assignment:
    assignment_id: str
    title: str
    allowed_template: str
    requirements: tuple[str, ...]


# отчёт анализа 

FindingKind = Literal["similarity", "rubric_feedback", "processing_error"]
EvidenceField = Literal["text", "code"]


@dataclass(frozen=True, slots=True)
class Evidence:
    """Включительный диапазон строк исходного содержимого, нумерация с 1."""

    submission_id: str
    field: EvidenceField
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class Finding:
    kind: FindingKind
    score: float | None  # None — численная оценка не определена (это не ошибка).
    evidence: tuple[Evidence, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    report_id: str
    submission_id: str
    submission_hash: str
    analyzer_id: str
    analyzer_version: str
    config_hash: str
    findings: tuple[Finding, ...]
    created_at: str
    review_required: bool
