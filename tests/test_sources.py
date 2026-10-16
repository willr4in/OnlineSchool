"""Контрактные тесты источников: один набор проверок для JSONL и in-memory адаптеров."""

from collections.abc import Callable
from pathlib import Path

import pytest

from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.adapters.sources import InMemorySource, JSONLSource
from school_lab.services.intake import SubmissionService, import_source
from school_lab.services.ports import SubmissionSource

from conftest import DATA_DIR, load_public_submissions

PUBLIC = load_public_submissions()

SOURCE_FACTORIES: dict[str, Callable[[], SubmissionSource]] = {
    "memory": lambda: InMemorySource(PUBLIC),
    "jsonl": lambda: JSONLSource(DATA_DIR / "submissions.jsonl"),
}


@pytest.fixture(params=sorted(SOURCE_FACTORIES))
def source(request: pytest.FixtureRequest) -> SubmissionSource:
    return SOURCE_FACTORIES[request.param]()


# --- общий контракт ------------------------------------------------------------------

def test_source_keeps_order_numbers_and_data(source: SubmissionSource) -> None:
    with source.open() as records:
        loaded = list(records)  # Накопление допустимо только для малого тестового набора.
    assert [r.line_no for r in loaded] == list(range(1, len(PUBLIC) + 1))
    assert [r.raw for r in loaded] == PUBLIC
    assert all(r.error is None for r in loaded)


def test_source_can_be_reopened(source: SubmissionSource) -> None:
    with source.open() as records:
        first = [r.raw for r in records]
    with source.open() as records:
        second = [r.raw for r in records]
    assert first == second


def test_consumer_cannot_change_source_data(source: SubmissionSource) -> None:
    with source.open() as records:
        record = next(records)
        assert isinstance(record.raw, dict)
        record.raw["student_id"] = "изменено потребителем"
        record.raw["ai_declaration"]["used"] = True
    with source.open() as records:
        assert next(records).raw == PUBLIC[0]


def test_both_sources_give_same_import_result() -> None:
    results = []
    for factory in SOURCE_FACTORIES.values():
        results.append(import_source(factory(), SubmissionService(InMemorySubmissionRepository())).to_dict())
    assert results[0] == results[1]
    assert len(results[0]["accepted"]) == 12  # type: ignore[arg-type]


# --- ресурс JSONL: кто владеет файлом и когда он закрывается -------------------------

def test_jsonl_closes_file_after_full_read() -> None:
    source = JSONLSource(DATA_DIR / "submissions.jsonl")
    with source.open() as records:
        for _ in records:
            pass
        assert source.last_closed is False
    assert source.last_closed is True


def test_jsonl_closes_file_on_early_exit() -> None:
    source = JSONLSource(DATA_DIR / "submissions.jsonl")
    with source.open() as records:
        for record in records:
            if record.line_no == 2:
                break  # досрочное прекращение обработки
    assert source.last_closed is True


def test_jsonl_closes_file_on_consumer_error() -> None:
    source = JSONLSource(DATA_DIR / "submissions.jsonl")
    with pytest.raises(RuntimeError, match="ошибка потребителя"):
        with source.open() as records:
            next(records)
            raise RuntimeError("ошибка потребителя")
    assert source.last_closed is True  # ресурс освобождён, а исключение не подавлено


def test_jsonl_iterator_is_unusable_after_context() -> None:
    source = JSONLSource(DATA_DIR / "submissions.jsonl")
    with source.open() as records:
        next(records)
    with pytest.raises(ValueError):  # I/O operation on closed file
        next(records)


def test_jsonl_missing_file_is_source_error_not_record_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        with JSONLSource(tmp_path / "missing.jsonl").open():
            pass


def test_jsonl_broken_line_does_not_stop_reading(tmp_path: Path) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text('{"a": 1}\n{broken\n\n{"b": 2}\n', encoding="utf-8")
    with JSONLSource(path).open() as records:
        loaded = list(records)
    assert [(r.line_no, r.error.code if r.error else None) for r in loaded] == [
        (1, None),
        (2, "invalid_json"),
        (3, "invalid_json"),
        (4, None),
    ]
    assert loaded[3].raw == {"b": 2}
