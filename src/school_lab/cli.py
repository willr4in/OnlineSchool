"""Командная строка — адаптер поверх сервисов."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from school_lab.adapters.sources import JSONLSource
from school_lab.app import build_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="school-lab", description="Приём учебных сдач")
    commands = parser.add_subparsers(dest="command", required=True)

    import_cmd = commands.add_parser("import", help="Импорт файла сдач")
    import_cmd.add_argument("path", type=Path, help="JSONL-файл")
    return parser


def _fail(code: str, message: str) -> int:
    print(json.dumps({"code": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    return 2


def _cmd_import(path: Path) -> int:
    app = build_application()
    try:
        summary = app.import_from(JSONLSource(path))
    except (OSError, UnicodeError) as exc:
        return _fail("source_unavailable", str(exc))
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 1 if summary.errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _cmd_import(args.path)


if __name__ == "__main__":
    raise SystemExit(main())