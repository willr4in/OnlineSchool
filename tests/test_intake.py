import copy
import json
from pathlib import Path

import pytest

from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.adapters.sources import JSONLSource
from school_lab.domain.errors import SubmissionError
from school_lab.services.intake import SubmissionService, import_source

from conftest import RAW_EXAMPLE, changed


def test_valid_submission_is_accepted(service: SubmissionService, raw_submission: dict[str, object]) -> None:
    result = service.accept(raw_submission)
    assert result.status == "accepted"
    assert result.submission_id == "sub-001"
    assert len(result.content_hash) == 64


def test_duplicate_returns_already_accepted_and_does_not_grow(
    service: SubmissionService, repository: InMemorySubmissionRepository
) -> None:
    first = service.accept(copy.deepcopy(RAW_EXAMPLE))
    second = service.accept(copy.deepcopy(RAW_EXAMPLE))
    assert second.status == "duplicate"
    assert second.submission is first.submission  # возвращается уже принятая сдача
    assert len(repository) == 1


def test_conflict_does_not_overwrite_original(
    service: SubmissionService, repository: InMemorySubmissionRepository
) -> None:
    service.accept(copy.deepcopy(RAW_EXAMPLE))
    original = repository.get("sub-001")
    with pytest.raises(SubmissionError) as caught:
        service.accept(changed(code="print('другая версия')\n"))
    assert caught.value.code == "conflict"
    assert caught.value.field == "submission_id"
    assert repository.get("sub-001") == original
    assert len(repository) == 1


def test_new_version_with_new_id_keeps_both(
    service: SubmissionService, repository: InMemorySubmissionRepository
) -> None:
    service.accept(copy.deepcopy(RAW_EXAMPLE))
    result = service.accept(changed(submission_id="sub-001-v2", code="print('вторая версия')\n"))
    assert result.status == "accepted"
    assert len(repository) == 2
    assert repository.get("sub-001") is not None


@pytest.mark.parametrize("student_id", ["", " ", None, 42])
def test_invalid_submission_is_not_stored(
    service: SubmissionService, raw_submission: dict[str, object], student_id: object
) -> None:
    raw_submission["student_id"] = student_id
    with pytest.raises(SubmissionError) as caught:
        service.accept(raw_submission)
    assert caught.value.code == "schema_error"
    assert service.repository.get("sub-001") is None


def test_repository_refuses_overwrite_directly(service: SubmissionService) -> None:
    accepted = service.accept(copy.deepcopy(RAW_EXAMPLE)).submission
    repo = InMemorySubmissionRepository()
    repo.add(accepted)
    with pytest.raises(SubmissionError):
        repo.add(accepted)


def test_import_continues_after_broken_line(service: SubmissionService, tmp_path: Path) -> None:
    lines = [
        json.dumps(RAW_EXAMPLE),
        "{broken",
        json.dumps(RAW_EXAMPLE),
        json.dumps(changed(text="Другое содержимое с тем же ID")),
        json.dumps(changed(submission_id="bad", student_id="")),
        json.dumps(changed(submission_id="sub-002", student_id="student-002")),
    ]
    path = tmp_path / "mixed.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = import_source(JSONLSource(path), service)
    assert summary.accepted == ["sub-001", "sub-002"]
    assert summary.duplicate == ["sub-001"]
    assert [(e["line_no"], e["code"]) for e in summary.errors] == [
        (2, "invalid_json"),
        (4, "conflict"),
        (5, "schema_error"),
    ]
