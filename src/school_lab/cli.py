"""Командная строка — ещё один адаптер поверх тех же сервисов.

Коды завершения: 0 — всё успешно; 1 — ошибки отдельных строк или анализов;
2 — источник или файл заданий недоступен. Машинный JSON — в stdout, диагностика — в stderr.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from school_lab.adapters.sources import JSONLSource, load_assignments
from school_lab.app import build_application
from school_lab.domain.errors import AnalysisFailure, SubmissionError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="school-lab", description="Приём учебных сдач и анализ")
    commands = parser.add_subparsers(dest="command", required=True)

    import_cmd = commands.add_parser("import", help="Импорт файла сдач")
    import_cmd.add_argument("path", type=Path, help="JSONL-файл: один объект — одна версия сдачи")

    analyze_cmd = commands.add_parser("analyze", help="Импорт и запуск анализаторов")
    analyze_cmd.add_argument("path", type=Path)
    analyze_cmd.add_argument("--assignments", type=Path, required=True, help="assignments.json")
    analyze_cmd.add_argument(
        "--analyzer", action="append", dest="analyzers", help="Имя анализатора (по умолчанию — все)"
    )
    return parser


def _fail(code: str, message: str) -> int:
    print(json.dumps({"code": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    return 2


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_import(path: Path) -> int:
    app = build_application()
    try:
        summary = app.import_from(JSONLSource(path))
    except (OSError, UnicodeError) as exc:
        return _fail("source_unavailable", str(exc))
    _print(summary.to_dict())
    return 1 if summary.errors else 0


def _cmd_analyze(path: Path, assignments_path: Path, analyzers: list[str] | None) -> int:
    try:
        assignments = load_assignments(assignments_path)
    except (OSError, UnicodeError) as exc:
        return _fail("source_unavailable", str(exc))
    except SubmissionError as exc:
        return _fail("invalid_assignments", f"{exc.field}: {exc.message}")
    app = build_application(assignments)
    try:
        summary = app.import_from(JSONLSource(path))
    except (OSError, UnicodeError) as exc:
        return _fail("source_unavailable", str(exc))

    names = analyzers or list(app.registry.names())
    reports: list[dict[str, object]] = []
    analysis_errors: list[dict[str, str]] = []
    for submission_id in summary.accepted:
        for name in names:
            try:
                reports.append(asdict(app.analyze(submission_id, name)))
            except AnalysisFailure as exc:
                analysis_errors.append({"submission_id": submission_id, "analyzer": name, "message": str(exc)})
    _print({"import": summary.to_dict(), "reports": reports, "analysis_errors": analysis_errors})
    return 1 if summary.errors or analysis_errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import":
        return _cmd_import(args.path)
    return _cmd_analyze(args.path, args.assignments, args.analyzers)


if __name__ == "__main__":
    raise SystemExit(main())
