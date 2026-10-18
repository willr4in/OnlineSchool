"""Сервис анализа и реестр фабрик анализаторов."""

from collections.abc import Callable

from school_lab.domain.analysis import AnalysisContext, Analyzer, validate_report
from school_lab.domain.errors import AnalysisFailure
from school_lab.domain.models import AnalysisReport
from school_lab.services.ports import SubmissionRepository

AnalyzerFactory = Callable[[], Analyzer]


class AnalyzerRegistry:
    """Явный реестр фабрик. Создаётся при сборке приложения и передаётся сервису."""

    def __init__(self) -> None:
        self._factories: dict[str, AnalyzerFactory] = {}

    def register(self, name: str, factory: AnalyzerFactory) -> None:
        if not name.strip():
            raise AnalysisFailure("Имя анализатора не может быть пустым")
        if name in self._factories:
            raise AnalysisFailure(f"Анализатор {name!r} уже зарегистрирован")
        self._factories[name] = factory

    def create(self, name: str) -> Analyzer:
        try:
            factory = self._factories[name]
        except KeyError as exc:
            raise AnalysisFailure(f"Неизвестный анализатор: {name}") from exc
        analyzer = factory()
        if analyzer.analyzer_id != name:
            raise AnalysisFailure(f"Имя регистрации {name!r} не совпадает с analyzer_id")
        return analyzer

    def names(self) -> tuple[str, ...]:
        return tuple(self._factories)


class AnalysisService:
    def __init__(self, repository: SubmissionRepository, registry: AnalyzerRegistry) -> None:
        self.repository = repository
        self.registry = registry

    def run(self, submission_id: str, analyzer_name: str, context: AnalysisContext) -> AnalysisReport:
        submission = self.repository.get(submission_id)
        if submission is None:
            raise AnalysisFailure(f"Сдача {submission_id!r} не принята; анализ невозможен")
        if submission.assignment_id != context.assignment.assignment_id:
            raise AnalysisFailure("Контекст относится к другому заданию")
        analyzer = self.registry.create(analyzer_name)
        try:
            report = analyzer.analyze(submission, context)
        except AnalysisFailure:
            raise
        except Exception as exc:
            # Граница анализатора: дефект становится понятным отказом, причина сохраняется в __cause__.
            raise AnalysisFailure(
                f"Анализатор {analyzer_name!r} завершился ошибкой: {type(exc).__name__}: {exc}"
            ) from exc
        validate_report(report, submission, context)
        if report.analyzer_id != analyzer.analyzer_id or report.analyzer_version != analyzer.analyzer_version:
            raise AnalysisFailure("Отчёт не соответствует вызванному анализатору")
        return report
