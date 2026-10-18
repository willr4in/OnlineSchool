import json
from pathlib import Path

from school_lab.adapters.declaration import DeclarationAnalyzer
from school_lab.adapters.sources import JSONLSource, load_assignments
from school_lab.app import build_application

DATA = Path(__file__).resolve().parents[1] / "data"


def show(title: str, payload: object) -> None:
    print(f"\n=== {title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    assignments = load_assignments(DATA / "assignments.json")
    first_line = (DATA / "submissions.jsonl").read_text(encoding="utf-8").splitlines()[0]

    # 1–2. API-адаптер
    app = build_application(assignments)
    accepted = app.api.post_submission(first_line)
    show(f"POST sub-001 → {accepted.status}", accepted.body)
    duplicate = app.api.post_submission(first_line)
    show(f"POST sub-001 ещё раз → {duplicate.status}", duplicate.body)
    changed = json.loads(first_line) | {"text": "Изменённый текст под старым ID"}
    conflict = app.api.post_submission(json.dumps(changed, ensure_ascii=False))
    show(f"POST sub-001 с другим содержимым → {conflict.status}", conflict.body)
    stored = app.repository.get("sub-001")
    assert stored is not None
    print("Исходный текст не изменился:", stored.text)

    # 3. Импорт файла с ошибками
    summary = build_application(assignments).import_from(JSONLSource(DATA / "invalid_submissions.jsonl"))
    show("Импорт invalid_submissions.jsonl", summary.to_dict())

    # 4. Третий анализатор: одна строка конфигурации
    app = build_application(assignments, extra_analyzers={"declaration": DeclarationAnalyzer})
    app.import_from(JSONLSource(DATA / "submissions.jsonl"))
    print("\nЗарегистрированные анализаторы:", app.registry.names())
    for submission_id in ("sub-001", "sub-003"):
        report = app.analyze(submission_id, "declaration")
        print(f"{submission_id}: {report.findings[0].explanation} review_required={report.review_required}")


if __name__ == "__main__":
    main()
