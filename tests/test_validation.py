import copy
from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from school_lab.domain.errors import SubmissionError
from school_lab.domain.hashing import submission_hash
from school_lab.domain.validation import decode_json, parse_submission

from conftest import RAW_EXAMPLE, changed


def test_valid_submission_is_parsed_without_changes() -> None:
    raw = copy.deepcopy(RAW_EXAMPLE)
    submission = parse_submission(raw)
    assert asdict(submission) == RAW_EXAMPLE
    assert raw == RAW_EXAMPLE
    # Исходный код сохраняется со всеми переводами строк.
    assert submission.code == RAW_EXAMPLE["code"]


def test_submission_is_frozen() -> None:
    submission = parse_submission(copy.deepcopy(RAW_EXAMPLE))
    with pytest.raises(FrozenInstanceError):
        submission.student_id = "other"  # type: ignore[misc]


def test_timezone_z_is_accepted() -> None:
    assert parse_submission(changed(submitted_at="2026-09-01T07:01:00Z")).submitted_at.endswith("Z")


def _decl(**updates: object) -> dict[str, object]:
    base: dict[str, object] = {"used": False, "tool": None, "purpose": None, "verified_by_student": True}
    base.update(updates)
    return base


def _without(key: str) -> dict[str, object]:
    result = copy.deepcopy(RAW_EXAMPLE)
    del result[key]
    return result


def _decl_without(key: str) -> dict[str, object]:
    declaration = _decl()
    del declaration[key]
    return changed(ai_declaration=declaration)


# Общий набор ошибочных входов: используется и для доменного парсера, и для Pydantic-адаптера.
INVALID_CASES = [
    pytest.param(changed(schema_version=True), "schema_error", "schema_version", id="version-bool"),
    pytest.param(changed(schema_version="1"), "schema_error", "schema_version", id="version-str"),
    pytest.param(changed(schema_version=2), "unsupported_version", "schema_version", id="version-2"),
    pytest.param(changed(student_id=""), "schema_error", "student_id", id="empty-student"),
    pytest.param(changed(student_id="   "), "schema_error", "student_id", id="blank-student"),
    pytest.param(changed(student_id=None), "schema_error", "student_id", id="null-student"),
    pytest.param(changed(student_id=42), "schema_error", "student_id", id="int-student"),
    pytest.param(changed(submission_id=""), "schema_error", "submission_id", id="empty-id"),
    pytest.param(changed(submitted_at="2026-09-01T10:00:00"), "schema_error", "submitted_at", id="no-tz"),
    pytest.param(changed(submitted_at="01.09.2026 10:00"), "schema_error", "submitted_at", id="bad-ts"),
    pytest.param(changed(submitted_at=1756710000), "schema_error", "submitted_at", id="ts-number"),
    pytest.param(changed(code=123), "schema_error", "code", id="code-int"),
    pytest.param(changed(text=["a"]), "schema_error", "text", id="text-list"),
    pytest.param(changed(text=" ", code="\n"), "schema_error", "text/code", id="empty-work"),
    pytest.param(changed(template_id=" "), "schema_error", "template_id", id="blank-template"),
    pytest.param(changed(studnet_id="x"), "schema_error", "studnet_id", id="unknown-field"),
    pytest.param(_without("student_id"), "schema_error", "student_id", id="missing-field"),
    pytest.param(changed(ai_declaration=None), "schema_error", "ai_declaration", id="decl-null"),
    pytest.param(changed(ai_declaration=[]), "schema_error", "ai_declaration", id="decl-list"),
    pytest.param(
        changed(ai_declaration=_decl(used=True)), "schema_error", "ai_declaration", id="decl-used-no-tool"
    ),
    pytest.param(
        changed(ai_declaration=_decl(used="false")), "schema_error", "ai_declaration.used", id="decl-str-bool"
    ),
    pytest.param(
        changed(ai_declaration=_decl(used=True, tool="", purpose="x")),
        "schema_error", "ai_declaration.tool", id="decl-empty-tool",
    ),
    pytest.param(
        _decl_without("verified_by_student"),
        "schema_error", "ai_declaration.verified_by_student", id="decl-missing-nested",
    ),
    pytest.param(
        changed(ai_declaration={**_decl(), "model": "x"}), "schema_error", "ai_declaration.model",
        id="decl-unknown-nested",
    ),
    pytest.param([RAW_EXAMPLE], "schema_error", "submission", id="list-instead-of-object"),
]


@pytest.mark.parametrize(("raw", "code", "field"), INVALID_CASES)
def test_invalid_submission_gives_explainable_error(raw: object, code: str, field: str) -> None:
    before = copy.deepcopy(raw)
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw)
    assert caught.value.code == code
    assert caught.value.field == field
    assert caught.value.message
    assert set(caught.value.to_dict()) == {"code", "field", "message"}
    assert raw == before, "валидатор не должен изменять вход"


@pytest.mark.parametrize(
    "line",
    [
        "{broken",
        "",
        "   ",
        '{"a": 1, "a": 2}',
        '{"score": NaN}',
        '{"score": Infinity}',
    ],
)
def test_decode_json_rejects_bad_json(line: str) -> None:
    with pytest.raises(SubmissionError) as caught:
        decode_json(line)
    assert caught.value.code == "invalid_json"


def test_json_error_and_schema_error_are_distinguished() -> None:
    # Синтаксически корректный JSON с неверной схемой — это schema_error, а не invalid_json.
    with pytest.raises(SubmissionError) as caught:
        parse_submission(decode_json('{"schema_version": 1}'))
    assert caught.value.code == "schema_error"


def test_hash_ignores_key_order_but_not_content() -> None:
    submission = parse_submission(copy.deepcopy(RAW_EXAMPLE))
    reordered = dict(reversed(list(copy.deepcopy(RAW_EXAMPLE).items())))
    assert submission_hash(parse_submission(reordered)) == submission_hash(submission)
    assert submission_hash(replace(submission, code=submission.code + "\n")) != submission_hash(submission)
    assert submission_hash(replace(submission, student_id="other")) != submission_hash(submission)
