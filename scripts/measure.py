"""Измерения для отчёта ЛР 1 (траектория Backend).

Запуск:  python scripts/measure.py [N]
Печатает markdown-таблицы. Числа зависят от машины; важны соотношения.
Время — лучшее из 3 запусков; память — пик tracemalloc в отдельном запуске
(tracemalloc сильно замедляет код, поэтому время и память меряются раздельно).
"""

import copy
import gc
import json
import sys
import tempfile
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from school_lab.adapters.analyzers import LengthAnalyzer, TemplateAnalyzer
from school_lab.adapters.api import SubmissionIn
from school_lab.adapters.sources import InMemorySource, JSONLSource, load_assignments
from school_lab.app import build_application
from school_lab.domain.analysis import AnalysisContext
from school_lab.domain.models import AIDeclaration, Submission
from school_lab.domain.validation import parse_submission

ROOT = Path(__file__).resolve().parents[1]


def synthetic(n: int) -> list[dict[str, object]]:
    lines = (ROOT / "data/submissions.jsonl").read_text(encoding="utf-8").splitlines()
    base = [json.loads(line) for line in lines]
    result = []
    for i in range(n):
        item = copy.deepcopy(base[i % len(base)])
        item["submission_id"] = f"syn-{i:06d}"
        result.append(item)
    return result


def best_time(action: Callable[[], object], repeat: int = 3) -> float:
    times = []
    for _ in range(repeat):
        gc.collect()
        start = perf_counter()
        action()
        times.append((perf_counter() - start) * 1000)
    return min(times)


def peak_memory(action: Callable[[], object]) -> float:
    gc.collect()
    tracemalloc.start()
    action()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 2**20


@dataclass(frozen=True)
class SubmissionNoSlots:
    schema_version: int
    submission_id: str
    student_id: str
    assignment_id: str
    submitted_at: str
    text: str
    code: str
    template_id: str | None
    ai_declaration: AIDeclaration


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
    values = synthetic(n)
    print(f"Python {sys.version.split()[0]}, N = {n}\n")

    # --- 1. источники и импорт
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "big.jsonl"
        path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), encoding="utf-8")

        def stream_only() -> int:
            count = 0
            with JSONLSource(path).open() as records:
                for _ in records:
                    count += 1
            return count

        rows: list[tuple[str, Callable[[], object]]] = [
            ("Импорт JSONL → сервис приёма", lambda: build_application().import_from(JSONLSource(path))),
            ("Импорт InMemory → сервис приёма", lambda: build_application().import_from(InMemorySource(values))),
            ("Только чтение JSONL построчно", stream_only),
            ("Только чтение файла целиком в список", lambda: path.read_text(encoding="utf-8").splitlines()),
        ]
        print("| Операция | Время, мс | Пик памяти, МБ |\n|---|---:|---:|")
        for name, action in rows:
            print(f"| {name} | {best_time(action):.1f} | {peak_memory(action):.2f} |")

    # --- 2. два пути валидации: доменный парсер и Pydantic DTO
    lines = [json.dumps(v, ensure_ascii=False) for v in values]
    validation_rows: list[tuple[str, Callable[[], object]]] = [
        ("Домен: parse_submission(dict)", lambda: [parse_submission(v) for v in values]),
        ("Pydantic: model_validate(dict) + to_domain()",
         lambda: [SubmissionIn.model_validate(v).to_domain() for v in values]),
        ("API-адаптер: post_submission(JSON-строка)", lambda: _post_all(lines)),
    ]
    print("\n| Путь валидации | Всего, мс | На запись, мкс |\n|---|---:|---:|")
    for name, action in validation_rows:
        ms = best_time(action)
        print(f"| {name} | {ms:.1f} | {ms / n * 1000:.1f} |")

    # --- 3. анализаторы
    context = AnalysisContext(load_assignments(ROOT / "data/assignments.json")["assignment-01"])
    submissions = [parse_submission(v) for v in values]
    print("\n| Анализатор | Всего, мс | На сдачу, мкс |\n|---|---:|---:|")
    for analyzer in (LengthAnalyzer(), TemplateAnalyzer()):
        ms = best_time(lambda a=analyzer: [a.analyze(s, context) for s in submissions])  # type: ignore[misc]
        print(f"| {type(analyzer).__name__} | {ms:.1f} | {ms / n * 1000:.1f} |")

    # --- 4. slots=True против обычного dataclass
    raw = [asdict(s) for s in submissions]

    def build(cls: type[Submission] | type[SubmissionNoSlots]) -> list[object]:
        return [cls(**{**r, "ai_declaration": AIDeclaration(**r["ai_declaration"])}) for r in raw]

    slots_mb = peak_memory(lambda: build(Submission))
    dict_mb = peak_memory(lambda: build(SubmissionNoSlots))
    print(
        f"\nПамять {n} моделей: slots={slots_mb:.2f} МБ, без slots={dict_mb:.2f} МБ "
        f"(экономия {100 * (1 - slots_mb / dict_mb):.0f}%)"
    )


def _post_all(lines: list[str]) -> None:
    api = build_application().api
    for line in lines:
        api.post_submission(line)


if __name__ == "__main__":
    main()
