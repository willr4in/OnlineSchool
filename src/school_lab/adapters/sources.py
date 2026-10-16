"""Адаптеры источников сдач: JSONL-файл и in-memory коллекция (порт — services.ports.SubmissionSource)."""

import copy
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from school_lab.domain.errors import SubmissionError
from school_lab.domain.models import Assignment
from school_lab.domain.validation import decode_json, parse_assignments
from school_lab.services.ports import SourceRecord


class InMemorySource:
    """Выдаёт глубокие копии: потребитель не может изменить исходную коллекцию."""

    def __init__(self, values: Sequence[object]) -> None:
        self._values = copy.deepcopy(list(values))

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        def records() -> Iterator[SourceRecord]:
            for number, raw in enumerate(self._values, start=1):
                yield SourceRecord(number, raw=copy.deepcopy(raw))

        yield records()


class JSONLSource:
    """Построчное чтение JSONL. Пустая строка — invalid_json с продолжением чтения."""

    def __init__(self, path: Path, *, encoding: str = "utf-8") -> None:
        self.path = path
        self.encoding = encoding
        self.last_closed: bool | None = None  # Диагностика для тестов освобождения ресурса.

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        handle = self.path.open("r", encoding=self.encoding)
        self.last_closed = False
        try:
            with handle:

                def records() -> Iterator[SourceRecord]:
                    for number, line in enumerate(handle, start=1):
                        try:
                            raw = decode_json(line)
                        except SubmissionError as exc:
                            yield SourceRecord(number, error=exc)
                        else:
                            yield SourceRecord(number, raw=raw)

                yield records()
        finally:
            self.last_closed = handle.closed


def load_assignments(path: Path) -> dict[str, Assignment]:
    """Адаптер файла assignments.json. Разбор и проверка — в parsing.parse_assignments."""
    with path.open("r", encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise SubmissionError("invalid_json", "assignments", f"Ошибка JSON в строке {exc.lineno}") from exc
    return parse_assignments(raw)
