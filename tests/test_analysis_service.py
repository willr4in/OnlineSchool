"""Сервис анализа и реестр фабрик анализаторов."""

import copy
from dataclasses import asdict, replace

import pytest

from school_lab.adapters.analyzers import LengthAnalyzer, TemplateAnalyzer
from school_lab.adapters.memory import InMemorySubmissionRepository
from school_lab.domain.analysis import AnalysisContext, make_report
from school_lab.domain.errors import AnalysisFailure
from school_lab.domain.models import AnalysisReport, Assignment, Finding, Submission
from school_lab.services.analysis import AnalysisService, AnalyzerRegistry
from school_lab.services.intake import SubmissionService

from conftest import RAW_EXAMPLE, changed

ASSIGNMENT = Assignment("assignment-01", "Сумма квадратов", "from typing import Iterable\n", ("Функция solve",))
CONTEXT = AnalysisContext(ASSIGNMENT)


@pytest.fixture
def registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    registry.register("length", LengthAnalyzer)
    registry.register("template", TemplateAnalyzer)
    return registry


@pytest.fixture
def analysis(repository: InMemorySubmissionRepository, registry: AnalyzerRegistry) -> AnalysisService:
    SubmissionService(repository).accept(copy.deepcopy(RAW_EXAMPLE))
    return AnalysisService(repository, registry)


# --- тестовые анализаторы -----------------------------------------------------------

class CrashingAnalyzer:
    analyzer_id = "crashing"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        raise ZeroDivisionError("дефект внутри анализатора")


class WrongHashAnalyzer:
    analyzer_id = "wrong-hash"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        return replace(LengthAnalyzer().analyze(submission, context), submission_hash="incorrect")


class ImpostorAnalyzer:
    """Выдаёт отчёт от имени другого анализатора."""

    analyzer_id = "impostor"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        return LengthAnalyzer().analyze(submission, context)


class MissingExplanationAnalyzer:
    """Упражнение 3: сообщает о пустом text при непустом code. Подключается только регистрацией."""

    analyzer_id = "missing-explanation"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        missing = not submission.text.strip() and bool(submission.code.strip())
        explanation = "Пояснение к коду отсутствует." if missing else "Пояснение к коду присутствует."
        finding = Finding("rubric_feedback", None, (), explanation)
        return make_report(
            submission, context, self.analyzer_id, self.analyzer_version, (finding,), review_required=missing
        )


# --- сервис ------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["length", "template"])
def test_service_runs_registered_analyzers(analysis: AnalysisService, name: str) -> None:
    report = analysis.run("sub-001", name, CONTEXT)
    assert report.analyzer_id == name


def test_third_analyzer_without_changing_service(
    analysis: AnalysisService, registry: AnalyzerRegistry, repository: InMemorySubmissionRepository
) -> None:
    registry.register("missing-explanation", MissingExplanationAnalyzer)
    SubmissionService(repository).accept(changed(submission_id="sub-no-text", text=""))
    assert analysis.run("sub-001", "missing-explanation", CONTEXT).review_required is False
    assert analysis.run("sub-no-text", "missing-explanation", CONTEXT).review_required is True


def test_analyzer_error_becomes_analysis_failure_and_keeps_submission(
    analysis: AnalysisService, registry: AnalyzerRegistry, repository: InMemorySubmissionRepository
) -> None:
    registry.register("crashing", CrashingAnalyzer)
    before = asdict(repository.get("sub-001"))  # type: ignore[arg-type]
    with pytest.raises(AnalysisFailure, match="crashing") as caught:
        analysis.run("sub-001", "crashing", CONTEXT)
    assert isinstance(caught.value.__cause__, ZeroDivisionError)  # причина не потеряна
    assert asdict(repository.get("sub-001")) == before  # type: ignore[arg-type]
    assert len(repository) == 1


def test_defective_report_is_rejected(analysis: AnalysisService, registry: AnalyzerRegistry) -> None:
    registry.register("wrong-hash", WrongHashAnalyzer)
    with pytest.raises(AnalysisFailure, match="другую версию"):
        analysis.run("sub-001", "wrong-hash", CONTEXT)


def test_report_from_other_analyzer_is_rejected(analysis: AnalysisService, registry: AnalyzerRegistry) -> None:
    registry.register("impostor", ImpostorAnalyzer)
    with pytest.raises(AnalysisFailure, match="не соответствует"):
        analysis.run("sub-001", "impostor", CONTEXT)


def test_unknown_submission_and_wrong_context(analysis: AnalysisService) -> None:
    with pytest.raises(AnalysisFailure):
        analysis.run("sub-404", "length", CONTEXT)
    other = AnalysisContext(Assignment("assignment-02", "Другое", "", ()))
    with pytest.raises(AnalysisFailure):
        analysis.run("sub-001", "length", other)


# --- реестр -------------------------------------------------------------------------

def test_registry_rejects_bad_registrations(registry: AnalyzerRegistry) -> None:
    with pytest.raises(AnalysisFailure):
        registry.register("length", LengthAnalyzer)
    with pytest.raises(AnalysisFailure):
        registry.register(" ", LengthAnalyzer)
    with pytest.raises(AnalysisFailure, match="Неизвестный"):
        registry.create("nope")
    registry.register("alias", LengthAnalyzer)
    with pytest.raises(AnalysisFailure, match="не совпадает"):
        registry.create("alias")


def test_registry_factory_creates_new_instance(registry: AnalyzerRegistry) -> None:
    assert registry.create("length") is not registry.create("length")
