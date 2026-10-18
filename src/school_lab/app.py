"""Конфигурация приложения: единственное место, где выбираются конкретные реализации.

Сервисы получают зависимости через конструктор. Глобального изменяемого контейнера
нет: каждый вызов build_application() создаёт независимый набор объектов.
BUILTIN_ANALYZERS — неизменяемая таблица (MappingProxyType), а не глобальный реестр.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from school_lab.adapters.analyzers import LengthAnalyzer, TemplateAnalyzer
from school_lab.adapters.api import SubmissionApi
from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.domain.analysis import AnalysisContext
from school_lab.domain.errors import AnalysisFailure
from school_lab.domain.models import AnalysisReport, Assignment
from school_lab.services.analysis import AnalysisService, AnalyzerFactory, AnalyzerRegistry
from school_lab.services.intake import ImportSummary, SubmissionService, import_source
from school_lab.services.ports import SubmissionSource

BUILTIN_ANALYZERS: Mapping[str, AnalyzerFactory] = MappingProxyType({
    "length": LengthAnalyzer,
    "template": TemplateAnalyzer,
})


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Параметры анализа, входящие в config_hash отчётов."""

    mode: Literal["baseline", "stub"] = "baseline"
    config_version: str = "1"


@dataclass
class Application:
    config: AppConfig
    repository: InMemorySubmissionRepository
    registry: AnalyzerRegistry
    submission_service: SubmissionService
    analysis_service: AnalysisService
    api: SubmissionApi
    assignments: Mapping[str, Assignment]

    def import_from(self, source: SubmissionSource) -> ImportSummary:
        return import_source(source, self.submission_service)

    def context_for(self, submission_id: str) -> AnalysisContext:
        submission = self.repository.get(submission_id)
        if submission is None:
            raise AnalysisFailure(f"Сдача {submission_id!r} не принята")
        assignment = self.assignments.get(submission.assignment_id)
        if assignment is None:
            raise AnalysisFailure(f"Неизвестное задание {submission.assignment_id!r}")
        return AnalysisContext(
            assignment,
            mode=self.config.mode,
            config_version=self.config.config_version,
            submissions=self.repository,
        )

    def analyze(self, submission_id: str, analyzer_name: str) -> AnalysisReport:
        return self.analysis_service.run(submission_id, analyzer_name, self.context_for(submission_id))


def build_application(
    assignments: Mapping[str, Assignment] | None = None,
    *,
    config: AppConfig | None = None,
    extra_analyzers: Mapping[str, AnalyzerFactory] | None = None,
) -> Application:
    repository = InMemorySubmissionRepository()
    registry = AnalyzerRegistry()
    for name, factory in {**BUILTIN_ANALYZERS, **(extra_analyzers or {})}.items():
        registry.register(name, factory)
    submission_service = SubmissionService(repository)
    return Application(
        config=config or AppConfig(),
        repository=repository,
        registry=registry,
        submission_service=submission_service,
        analysis_service=AnalysisService(repository, registry),
        api=SubmissionApi(submission_service),
        assignments=dict(assignments or {}),
    )
