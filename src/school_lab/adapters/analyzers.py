"""Адаптеры-анализаторы"""

from school_lab.domain.analysis import AnalysisContext, make_report
from school_lab.domain.errors import AnalysisFailure
from school_lab.domain.models import AnalysisReport, Evidence, EvidenceField, Finding, Submission


def nonempty_line_numbers(text: str) -> tuple[int, ...]:
    """Номера (с 1) непустых строк исходного текста; сам текст не изменяется."""
    return tuple(number for number, line in enumerate(text.splitlines(), start=1) if line.strip())


def template_ranges(source: str, template: str) -> tuple[tuple[int, int], ...]:
    """Включительные диапазоны строк source, точно совпадающих с блоком строк template.

    Сравнение без нормализации пробелов; завершающий перевод строки не создаёт
    лишнюю строку (splitlines). Пустой шаблон не совпадает ни с чем.
    """
    if not template.strip():
        return ()
    source_lines = source.splitlines()
    template_lines = template.splitlines()
    width = len(template_lines)
    return tuple(
        (index + 1, index + width)
        for index in range(len(source_lines) - width + 1)
        if source_lines[index : index + width] == template_lines
    )


def _line_evidence(submission_id: str, field: EvidenceField, numbers: tuple[int, ...]) -> tuple[Evidence, ...]:
    return tuple(Evidence(submission_id, field, number, number) for number in numbers)


class LengthAnalyzer:
    analyzer_id = "length"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        text_lines = nonempty_line_numbers(submission.text)
        code_lines = nonempty_line_numbers(submission.code)
        evidence = _line_evidence(submission.submission_id, "text", text_lines) + _line_evidence(
            submission.submission_id, "code", code_lines
        )
        finding = Finding(
            kind="rubric_feedback",
            score=None,
            evidence=evidence,
            explanation=(
                f"Непустые строки: text={len(text_lines)}, code={len(code_lines)}. "
                "Объём работы не оценивает корректность решения, поэтому score не выставляется."
            ),
        )
        return make_report(submission, context, self.analyzer_id, self.analyzer_version, (finding,))


class TemplateAnalyzer:
    analyzer_id = "template"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        if submission.assignment_id != context.assignment.assignment_id:
            raise AnalysisFailure("Контекст относится к другому заданию")
        ranges = template_ranges(submission.code, context.assignment.allowed_template)
        evidence = tuple(Evidence(submission.submission_id, "code", start, end) for start, end in ranges)
        if ranges:
            explanation = (
                f"Найдены точные блоки разрешённого шаблона: {len(ranges)}. "
                "Совпадение с шаблоном разрешено и не является основанием для санкции."
            )
        else:
            explanation = "Точное совпадение с разрешённым шаблоном не найдено. Нечёткое сходство не проверялось."
        finding = Finding(kind="similarity", score=None, evidence=evidence, explanation=explanation)
        return make_report(submission, context, self.analyzer_id, self.analyzer_version, (finding,))
