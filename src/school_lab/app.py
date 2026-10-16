"""Конфигурация приложения: единственное место, где выбираются конкретные реализации."""

from dataclasses import dataclass
from collections.abc import Mapping

from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.adapters.api import SubmissionApi
from school_lab.domain.models import Assignment
from school_lab.services.intake import ImportSummary, SubmissionService, import_source
from school_lab.services.ports import SubmissionSource


@dataclass
class Application:
    repository: InMemorySubmissionRepository
    submission_service: SubmissionService
    api: SubmissionApi
    assignments: Mapping[str, Assignment]

    def import_from(self, source: SubmissionSource) -> ImportSummary:
        return import_source(source, self.submission_service)


def build_application(
    assignments: Mapping[str, Assignment] | None = None,
) -> Application:
    repository = InMemorySubmissionRepository()
    submission_service = SubmissionService(repository)
    return Application(
        repository=repository,
        submission_service=submission_service,
        api=SubmissionApi(submission_service),
        assignments=dict(assignments or {}),
    )