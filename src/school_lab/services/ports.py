"""Порты — интерфейсы, через которые сервисы работают с внешним миром."""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from school_lab.domain.errors import SubmissionError
from school_lab.domain.models import Submission


class SubmissionRepository(Protocol):
    def get(self, submission_id: str) -> Submission | None: ...
    def add(self, submission: Submission) -> None: ...


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Одна запись источника: номер строки и либо разобранный JSON, либо ошибка формата."""

    line_no: int
    raw: object = None
    error: SubmissionError | None = None


class SubmissionSource(Protocol):
    """open() — контекстный менеджер; он владеет ресурсом и закрывает его при выходе из with."""

    def open(self) -> AbstractContextManager[Iterator[SourceRecord]]: ...
