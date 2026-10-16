"""In-memory реализации портов."""

from collections.abc import Iterator

from school_lab.domain.errors import SubmissionError
from school_lab.domain.models import Submission


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._items: dict[str, Submission] = {}

    def get(self, submission_id: str) -> Submission | None:
        return self._items.get(submission_id)

    def add(self, submission: Submission) -> None:
        # Защита на уровне хранилища: даже при ошибке в сервисе запись не перезаписывается.
        if submission.submission_id in self._items:
            raise SubmissionError("conflict", "submission_id", "Идентификатор уже сохранён")
        self._items[submission.submission_id] = submission

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Submission]:
        return iter(list(self._items.values()))
