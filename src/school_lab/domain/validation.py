"""Разбор JSON и валидация схемы сдачи."""

import json
from collections.abc import Mapping
from datetime import datetime

from school_lab.domain.errors import SubmissionError
from school_lab.domain.models import AIDeclaration, Assignment, Submission

SUPPORTED_SCHEMA_VERSION = 1

SUBMISSION_FIELDS = frozenset({
    "schema_version", "submission_id", "student_id", "assignment_id", "submitted_at",
    "text", "code", "template_id", "ai_declaration",
})
DECLARATION_FIELDS = frozenset({"used", "tool", "purpose", "verified_by_student"})


# JSON

def _reject_repeated_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SubmissionError("invalid_json", key, "Повтор ключа в JSON-объекте не допускается")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise SubmissionError("invalid_json", "json", f"Нестандартное значение не допускается: {value}")


def decode_json(line: str) -> object:
    """Строгий json.loads: без повторных ключей, NaN и Infinity."""
    try:
        return json.loads(line, object_pairs_hook=_reject_repeated_keys, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise SubmissionError("invalid_json", "json", f"Ошибка JSON около столбца {exc.colno}: {exc.msg}") from exc


# элементарные проверки

def require_object(raw: object, name: str) -> Mapping[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise SubmissionError("schema_error", name, "Ожидается JSON-объект со строковыми ключами")
    return raw


def require_fields(raw: Mapping[str, object], expected: frozenset[str], prefix: str = "") -> None:
    missing = expected - raw.keys()
    extra = raw.keys() - expected
    if missing:
        raise SubmissionError("schema_error", prefix + sorted(missing)[0], "Обязательное поле отсутствует")
    if extra:
        raise SubmissionError("schema_error", prefix + sorted(extra)[0], "Неизвестное поле не допускается")


def require_string(value: object, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise SubmissionError("schema_error", name, "Ожидается строка без преобразования типа")
    if nonempty and not value.strip():
        raise SubmissionError("schema_error", name, "Ожидается непустая строка")
    return value


def optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return require_string(value, name)


def require_bool(value: object, name: str) -> bool:
    # type(...) is bool: строка "false" и число 0 не превращаются в bool неявно.
    if type(value) is not bool:
        raise SubmissionError("schema_error", name, "Ожидается bool, а не строка или число")
    return value


def validate_timestamp(value: object, name: str = "submitted_at") -> str:
    text = require_string(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SubmissionError("schema_error", name, "Ожидается дата и время ISO 8601 с часовым поясом") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SubmissionError("schema_error", name, "Часовой пояс обязателен")
    return text


# сдача

def parse_declaration(raw: object) -> AIDeclaration:
    data = require_object(raw, "ai_declaration")
    require_fields(data, DECLARATION_FIELDS, "ai_declaration.")
    declaration = AIDeclaration(
        used=require_bool(data["used"], "ai_declaration.used"),
        tool=optional_string(data["tool"], "ai_declaration.tool"),
        purpose=optional_string(data["purpose"], "ai_declaration.purpose"),
        verified_by_student=require_bool(data["verified_by_student"], "ai_declaration.verified_by_student"),
    )
    if declaration.used and (declaration.tool is None or declaration.purpose is None):
        raise SubmissionError("schema_error", "ai_declaration", "При used=true обязательны инструмент и цель")
    return declaration


def parse_submission(raw: object) -> Submission:
    """Проверяет уже разобранный JSON-объект и строит Submission. Вход не изменяется."""
    data = require_object(raw, "submission")
    require_fields(data, SUBMISSION_FIELDS)

    version = data["schema_version"]
    if type(version) is not int:
        raise SubmissionError("schema_error", "schema_version", "Ожидается целое число; bool не допускается")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise SubmissionError(
            "unsupported_version", "schema_version", f"Поддерживается версия схемы {SUPPORTED_SCHEMA_VERSION}"
        )

    submission_id = require_string(data["submission_id"], "submission_id")
    student_id = require_string(data["student_id"], "student_id")
    assignment_id = require_string(data["assignment_id"], "assignment_id")
    submitted_at = validate_timestamp(data["submitted_at"])

    # strip() только для проверки пустоты: исходный текст сохраняется целиком,
    # иначе номера строк evidence будут относиться к изменённому содержимому.
    text = require_string(data["text"], "text", nonempty=False)
    code = require_string(data["code"], "code", nonempty=False)
    if not text.strip() and not code.strip():
        raise SubmissionError("schema_error", "text/code", "Текст или код должны быть непустыми")

    return Submission(
        schema_version=version,
        submission_id=submission_id,
        student_id=student_id,
        assignment_id=assignment_id,
        submitted_at=submitted_at,
        text=text,
        code=code,
        template_id=optional_string(data["template_id"], "template_id"),
        ai_declaration=parse_declaration(data["ai_declaration"]),
    )


# задания

ASSIGNMENT_FIELDS = frozenset({"assignment_id", "title", "allowed_template", "requirements"})


def parse_assignment(raw: object, name: str = "assignment") -> Assignment:
    data = require_object(raw, name)
    require_fields(data, ASSIGNMENT_FIELDS, name + ".")
    requirements = data["requirements"]
    if not isinstance(requirements, list):
        raise SubmissionError("schema_error", f"{name}.requirements", "Ожидается список строк")
    return Assignment(
        assignment_id=require_string(data["assignment_id"], f"{name}.assignment_id"),
        title=require_string(data["title"], f"{name}.title"),
        # Пустой шаблон допустим: он просто ни с чем не совпадает.
        allowed_template=require_string(data["allowed_template"], f"{name}.allowed_template", nonempty=False),
        requirements=tuple(
            require_string(item, f"{name}.requirements[{index}]") for index, item in enumerate(requirements)
        ),
    )


def parse_assignments(raw: object) -> dict[str, Assignment]:
    """assignments.json — JSON-массив заданий с уникальными assignment_id."""
    if not isinstance(raw, list):
        raise SubmissionError("schema_error", "assignments", "Ожидается JSON-массив заданий")
    result: dict[str, Assignment] = {}
    for index, item in enumerate(raw):
        assignment = parse_assignment(item, f"assignments[{index}]")
        if assignment.assignment_id in result:
            raise SubmissionError("conflict", f"assignments[{index}].assignment_id", "Повтор идентификатора задания")
        result[assignment.assignment_id] = assignment
    return result
