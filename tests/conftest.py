import copy
import json
from pathlib import Path

import pytest

from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.services.intake import SubmissionService

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

RAW_EXAMPLE: dict[str, object] = {
    "schema_version": 1,
    "submission_id": "sub-001",
    "student_id": "student-001",
    "assignment_id": "assignment-01",
    "submitted_at": "2026-09-01T10:01:00+03:00",
    "text": "Учебное решение с пояснением алгоритма.",
    "code": (
        "from typing import Iterable\n\n"
        "def solve(values: Iterable[int]) -> int:\n"
        "    return sum(x * x for x in values if x >= 0)\n"
    ),
    "template_id": "template-01",
    "ai_declaration": {"used": False, "tool": None, "purpose": None, "verified_by_student": True},
}


def changed(**updates: object) -> dict[str, object]:
    result = copy.deepcopy(RAW_EXAMPLE)
    result.update(updates)
    return result


def load_public_submissions() -> list[dict[str, object]]:
    text = (DATA_DIR / "submissions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


@pytest.fixture
def raw_submission() -> dict[str, object]:
    return copy.deepcopy(RAW_EXAMPLE)


@pytest.fixture
def repository() -> InMemorySubmissionRepository:
    return InMemorySubmissionRepository()


@pytest.fixture
def service(repository: InMemorySubmissionRepository) -> SubmissionService:
    return SubmissionService(repository)


@pytest.fixture
def data_dir() -> Path:
    return DATA_DIR
