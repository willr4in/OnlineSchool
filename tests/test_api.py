"""Pydantic-схемы, преобразование DTO → домен и тестовый API-адаптер."""

import copy
import json
from dataclasses import asdict

import pytest
from pydantic import ValidationError

from school_lab.adapters.api import STATUS_BY_CODE, SubmissionApi, SubmissionIn, validate_payload
from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.domain.errors import SubmissionError
from school_lab.domain.validation import parse_submission
from school_lab.services.intake import SubmissionService

from conftest import RAW_EXAMPLE, changed, load_public_submissions
from test_validation import INVALID_CASES


@pytest.fixture
def api(service: SubmissionService) -> SubmissionApi:
    return SubmissionApi(service)


def post(api: SubmissionApi, payload: object) -> tuple[int, dict[str, object]]:
    response = api.post_submission(json.dumps(payload, ensure_ascii=False))
    return response.status, response.body


# --- DTO → доменный объект ------------------------------------------------------------

@pytest.mark.parametrize("raw", load_public_submissions(), ids=lambda r: str(r["submission_id"]))
def test_dto_to_domain_matches_domain_parser(raw: dict[str, object]) -> None:
    before = copy.deepcopy(raw)
    assert SubmissionIn.model_validate(raw).to_domain() == parse_submission(raw)
    assert raw == before  # Pydantic-путь тоже не меняет вход


def test_dto_is_frozen_and_strict() -> None:
    dto = SubmissionIn.model_validate(copy.deepcopy(RAW_EXAMPLE))
    with pytest.raises(ValidationError):
        dto.student_id = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):  # strict: "1" не превращается в 1
        SubmissionIn.model_validate(changed(schema_version="1"))


@pytest.mark.parametrize(("raw", "code", "field"), INVALID_CASES)
def test_pydantic_path_gives_same_domain_errors(raw: object, code: str, field: str) -> None:
    """Оба пути входа (домен и Pydantic) дают одинаковые code и field."""
    before = copy.deepcopy(raw)
    with pytest.raises(SubmissionError) as caught:
        validate_payload(raw)
    assert (caught.value.code, caught.value.field) == (code, field)
    assert caught.value.message
    assert isinstance(caught.value.__cause__, ValidationError)  # причина сохранена
    assert raw == before


# --- статусы тестового адаптера ---------------------------------------------------------

def test_post_accepted_then_duplicate(api: SubmissionApi, repository: InMemorySubmissionRepository) -> None:
    status, body = post(api, RAW_EXAMPLE)
    assert status == 201 and body["status"] == "accepted"
    status, body = post(api, RAW_EXAMPLE)
    assert status == 200 and body["status"] == "duplicate"
    assert len(repository) == 1


def test_post_conflict_does_not_overwrite(api: SubmissionApi, repository: InMemorySubmissionRepository) -> None:
    post(api, RAW_EXAMPLE)
    original = repository.get("sub-001")
    status, body = post(api, changed(text="Другая версия под тем же ID"))
    assert status == 409
    assert body == {
        "code": "conflict",
        "field": "submission_id",
        "message": "Идентификатор занят другим содержимым; новой версии нужен новый ID",
    }
    assert repository.get("sub-001") == original


@pytest.mark.parametrize(
    ("body", "status", "code", "field"),
    [
        ("{broken", 400, "invalid_json", "json"),
        ('{"a": 1, "a": 2}', 400, "invalid_json", "a"),
        (b"\xff\xfe", 400, "invalid_json", "body"),
        (json.dumps(changed(student_id="")), 422, "schema_error", "student_id"),
        (json.dumps(changed(submitted_at="2026-09-01T10:00:00")), 422, "schema_error", "submitted_at"),
        (json.dumps(changed(studnet_id="x")), 422, "schema_error", "studnet_id"),
        (json.dumps(changed(schema_version=2)), 422, "unsupported_version", "schema_version"),
    ],
)
def test_post_errors(
    api: SubmissionApi, repository: InMemorySubmissionRepository, body: str | bytes, status: int, code: str, field: str
) -> None:
    response = api.post_submission(body)
    assert response.status == status
    assert response.body["code"] == code and response.body["field"] == field
    assert set(response.body) == {"code", "field", "message"}
    assert len(repository) == 0


def test_get_submission_converts_domain_to_output_model(api: SubmissionApi) -> None:
    post(api, RAW_EXAMPLE)
    response = api.get_submission("sub-001")
    assert response.status == 200
    assert {k: v for k, v in response.body.items() if k != "content_hash"} == RAW_EXAMPLE
    assert len(str(response.body["content_hash"])) == 64
    assert api.get_submission("nope").status == 404


def test_domain_errors_know_nothing_about_http() -> None:
    error = SubmissionError("conflict", "submission_id", "x")
    assert not hasattr(error, "status")
    assert set(error.to_dict()) == {"code", "field", "message"}
    assert set(STATUS_BY_CODE) == {"invalid_json", "schema_error", "unsupported_version", "conflict"}


def test_service_is_independent_from_adapter() -> None:
    """Тот же сервис работает и без API-адаптера: доменная модель передаётся напрямую."""
    service = SubmissionService(InMemorySubmissionRepository())
    submission = parse_submission(copy.deepcopy(RAW_EXAMPLE))
    assert service.accept_submission(submission).status == "accepted"
    assert asdict(service.get("sub-001")) == RAW_EXAMPLE  # type: ignore[arg-type]
