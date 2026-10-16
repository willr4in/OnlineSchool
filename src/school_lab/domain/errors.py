"""Доменные исключения."""

from typing import Literal

ErrorCode = Literal["invalid_json", "schema_error", "unsupported_version", "conflict"]


class SubmissionError(Exception):
    """Ошибка приёма одной сдачи: формат, схема, версия или конфликт идентификатора."""

    def __init__(self, code: ErrorCode, field: str, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}

    def __repr__(self) -> str:
        return f"SubmissionError({self.code!r}, {self.field!r}, {self.message!r})"


class AnalysisFailure(Exception):
    """Отказ анализа: неизвестный анализатор, неверный контекст или некорректный отчёт анализатора."""
