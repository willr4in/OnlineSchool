"""Третий анализатор (для защиты): проверяет, что при used=true AI-декларация непустая."""

from school_lab.domain.analysis import AnalysisContext, make_report
from school_lab.domain.models import AnalysisReport, Finding, Submission


class DeclarationAnalyzer:
    analyzer_id = "declaration"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        declaration = submission.ai_declaration
        missing = [
            name
            for name, value in (("tool", declaration.tool), ("purpose", declaration.purpose))
            if value is None or not value.strip()
        ]
        if not declaration.used:
            explanation = "Использование ИИ не заявлено. Авторство текста автоматически не определялось."
            review_required = False
        elif missing:
            explanation = f"Использование ИИ заявлено, но декларация неполная: пусто {', '.join(missing)}."
            review_required = True
        else:
            explanation = (
                f"Использование ИИ заявлено и декларация заполнена. Инструмент: {declaration.tool}; "
                f"цель: {declaration.purpose}."
            )
            review_required = not declaration.verified_by_student
        if declaration.used and not declaration.verified_by_student:
            explanation += " Студент не подтвердил проверку результата — нужна ручная проверка."
        finding = Finding(kind="rubric_feedback", score=None, evidence=(), explanation=explanation)
        return make_report(
            submission, context, self.analyzer_id, self.analyzer_version, (finding,), review_required=review_required
        )
