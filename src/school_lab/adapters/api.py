"""Входной адаптер: Pydantic-схемы и тестовый API-адаптер (замена HTTP до появления FastAPI)."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from school_lab.domain.errors import ErrorCode, SubmissionError
from school_lab.domain.hashing import submission_hash
from school_lab.domain.models import AIDeclaration, Submission
from school_lab.domain.validation import SUPPORTED_SCHEMA_VERSION, decode_json, validate_timestamp
from school_lab.services.intake import SubmissionService

STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


def _schema_error(message: str, field: str | None = None) -> PydanticCustomError:
    return PydanticCustomError("schema_error", message, {"field": field} if field else None)


# входные модели (DTO)

class DeclarationIn(BaseModel):
    model_config = STRICT

    used: bool
    tool: str | None
    purpose: str | None
    verified_by_student: bool

    @field_validator("tool", "purpose")
    @classmethod
    def _optional_nonempty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise _schema_error("Ожидается непустая строка")
        return value

    @model_validator(mode="after")
    def _used_requires_details(self) -> Self:
        if self.used and (self.tool is None or self.purpose is None):
            raise _schema_error("При used=true обязательны инструмент и цель")
        return self


class SubmissionIn(BaseModel):
    """Входная модель API. strict=True: "false" не станет bool, 1 не станет строкой."""

    model_config = STRICT

    schema_version: int
    submission_id: str
    student_id: str
    assignment_id: str
    submitted_at: str  # Строка сохраняется как есть: от представления зависит хеш сдачи.
    text: str
    code: str
    template_id: str | None
    ai_declaration: DeclarationIn

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, value: int) -> int:
        if value != SUPPORTED_SCHEMA_VERSION:
            raise PydanticCustomError(
                "unsupported_version", "Поддерживается версия схемы {version}", {"version": SUPPORTED_SCHEMA_VERSION}
            )
        return value

    @field_validator("submission_id", "student_id", "assignment_id", "template_id")
    @classmethod
    def _nonempty_identifier(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise _schema_error("Ожидается непустая строка")
        return value

    @field_validator("submitted_at")
    @classmethod
    def _timestamp(cls, value: str) -> str:
        try:
            return validate_timestamp(value)  # одна политика дат для домена и API
        except SubmissionError as exc:
            raise _schema_error(exc.message) from exc

    @model_validator(mode="after")
    def _has_content(self) -> Self:
        if not self.text.strip() and not self.code.strip():
            raise _schema_error("Текст или код должны быть непустыми", "text/code")
        return self

    def to_domain(self) -> Submission:
        """Преобразование входной модели в доменный объект."""
        declaration = self.ai_declaration
        return Submission(
            schema_version=self.schema_version,
            submission_id=self.submission_id,
            student_id=self.student_id,
            assignment_id=self.assignment_id,
            submitted_at=self.submitted_at,
            text=self.text,
            code=self.code,
            template_id=self.template_id,
            ai_declaration=AIDeclaration(
                used=declaration.used,
                tool=declaration.tool,
                purpose=declaration.purpose,
                verified_by_student=declaration.verified_by_student,
            ),
        )


class SubmissionOut(SubmissionIn):
    """Выходная модель: доменная сдача + её хеш."""

    content_hash: str

    @classmethod
    def from_domain(cls, submission: Submission, content_hash: str) -> "SubmissionOut":
        return cls.model_validate({**asdict(submission), "content_hash": content_hash})


# ValidationError

_MESSAGES_BY_TYPE: Mapping[str, str] = MappingProxyType({
    "missing": "Обязательное поле отсутствует",
    "extra_forbidden": "Неизвестное поле не допускается",
    "string_type": "Ожидается строка без преобразования типа",
    "bool_type": "Ожидается bool, а не строка или число",
    "int_type": "Ожидается целое число; bool не допускается",
    "model_type": "Ожидается JSON-объект",
    "dict_type": "Ожидается JSON-объект",
})


def to_submission_error(exc: ValidationError) -> SubmissionError:
    """Первая ошибка Pydantic → SubmissionError(code, field, message) в доменном формате."""
    error = exc.errors(include_url=False)[0]
    ctx = error.get("ctx") or {}
    field = ctx.get("field") or ".".join(str(part) for part in error["loc"]) or "submission"
    code: ErrorCode = "unsupported_version" if error["type"] == "unsupported_version" else "schema_error"
    message = _MESSAGES_BY_TYPE.get(error["type"], error["msg"])
    return SubmissionError(code, str(field), message)


def validate_payload(raw: object) -> Submission:
    """Pydantic-путь валидации: разобранный JSON - DTO - доменная модель."""
    try:
        return SubmissionIn.model_validate(raw).to_domain()
    except ValidationError as exc:
        raise to_submission_error(exc) from exc


# тестовый адаптер вместо HTTP

STATUS_BY_CODE: Mapping[ErrorCode, int] = MappingProxyType({
    "invalid_json": 400,
    "schema_error": 422,
    "unsupported_version": 422,
    "conflict": 409,
})


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    body: dict[str, object]


class SubmissionApi:
    """Тестовый адаптер с семантикой HTTP."""

    def __init__(self, service: SubmissionService) -> None:
        self.service = service

    def post_submission(self, body: str | bytes) -> ApiResponse:
        try:
            text = body.decode("utf-8") if isinstance(body, bytes) else body
            submission = validate_payload(decode_json(text))
            result = self.service.accept_submission(submission)
        except UnicodeDecodeError:
            return self._error(SubmissionError("invalid_json", "body", "Тело запроса должно быть в UTF-8"))
        except SubmissionError as exc:
            return self._error(exc)
        status = 201 if result.status == "accepted" else 200
        return ApiResponse(
            status,
            {"status": result.status, "submission_id": result.submission_id, "content_hash": result.content_hash},
        )

    def get_submission(self, submission_id: str) -> ApiResponse:
        submission = self.service.get(submission_id)
        if submission is None:
            return ApiResponse(404, {"code": "not_found", "field": "submission_id", "message": "Сдача не найдена"})
        out = SubmissionOut.from_domain(submission, submission_hash(submission))
        return ApiResponse(200, out.model_dump())

    @staticmethod
    def _error(exc: SubmissionError) -> ApiResponse:
        body: dict[str, object] = {**exc.to_dict()}
        return ApiResponse(STATUS_BY_CODE[exc.code], body)
