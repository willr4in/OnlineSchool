"""Сервис приёма сдач — независим от способа доставки данных (Pydantic/API, CLI, файл)."""

from dataclasses import asdict, dataclass, field
from typing import Literal

from school_lab.domain.errors import SubmissionError
from school_lab.domain.hashing import submission_hash
from school_lab.domain.models import Submission
from school_lab.domain.validation import parse_submission
from school_lab.services.ports import SubmissionRepository, SubmissionSource


@dataclass(frozen=True, slots=True)
class Acceptance:
    status: Literal["accepted", "duplicate"]
    submission: Submission
    content_hash: str

    @property
    def submission_id(self) -> str:
        return self.submission.submission_id


class SubmissionService:
    def __init__(self, repository: SubmissionRepository) -> None:
        self.repository = repository

    def accept(self, raw: object) -> Acceptance:
        """Вход «сырого» JSON-объекта: доменная валидация, затем приём."""
        return self.accept_submission(parse_submission(raw))

    def accept_submission(self, submission: Submission) -> Acceptance:
        """Вход уже валидированной доменной модели (например, после Pydantic DTO)."""
        digest = submission_hash(submission)
        previous = self.repository.get(submission.submission_id)
        if previous is not None:
            if submission_hash(previous) != digest:
                raise SubmissionError(
                    "conflict", "submission_id", "Идентификатор занят другим содержимым; новой версии нужен новый ID"
                )
            return Acceptance("duplicate", previous, digest)
        self.repository.add(submission)
        return Acceptance("accepted", submission, digest)

    def get(self, submission_id: str) -> Submission | None:
        return self.repository.get(submission_id)


@dataclass
class ImportSummary:
    accepted: list[str] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def import_source(source: SubmissionSource, service: SubmissionService) -> ImportSummary:
    """Импорт с частичным успехом: неверная запись попадает в errors с номером строки."""
    summary = ImportSummary()
    with source.open() as records:
        for record in records:
            if record.error is not None:
                summary.errors.append({"line_no": record.line_no, **record.error.to_dict()})
                continue
            try:
                result = service.accept(record.raw)
            except SubmissionError as exc:
                summary.errors.append({"line_no": record.line_no, **exc.to_dict()})
            else:
                target = summary.accepted if result.status == "accepted" else summary.duplicate
                target.append(result.submission_id)
    return summary
