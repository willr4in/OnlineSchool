# Отчёт по ЛР 1 «Приём работ и расширяемые анализаторы»

**Траектория:** Backend. **Уровень:** основной.

## 1. Выполненные требования

### Общие требования этапа А

| Требование | Где реализовано | Чем проверено |
|---|---|---|
| Пакет в src-layout, устанавливается в чистое окружение | `pyproject.toml`, `src/school_lab/` | `pip install .` в новом venv (раздел 2) |
| Модель `Submission` | `domain/models.py` (dataclass, frozen, slots) | `test_submission_is_frozen` |
| Разбор JSON, обязательные поля, timezone, AI-декларация | `domain/validation.py`, `adapters/api.py` | `test_invalid_submission_gives_explainable_error` (25 случаев) |
| Ошибка = `code`, `field`, `message` | `domain/errors.SubmissionError` | все тесты ошибок проверяют `code` и `field` |
| Вход не изменяется | валидация только читает | `assert raw == before` в доменном и Pydantic-путях |
| Формат / схема / конфликт различаются | `invalid_json` / `schema_error` (+`unsupported_version`) / `conflict` | `test_post_errors`, `test_cli.py` |
| Тот же ID + тот же хеш - уже принятая сдача | `SubmissionService.accept_submission` | `test_duplicate_returns_already_accepted_and_does_not_grow` |
| Тот же ID + другое содержимое - conflict без перезаписи | там же + защита в `InMemorySubmissionRepository.add` | `test_conflict_does_not_overwrite_original`, `test_post_conflict_does_not_overwrite` |
| In-memory репозиторий | `adapters/memory.py` | - |
| Публичные функции аннотированы | весь `src/` | `mypy --strict` без ошибок |
| Домен не читает stdin и не обращается к HTTP | `domain/` не импортирует ни Pydantic, ни ввод-вывод | структура пакета |

### Основной вариант Backend, этап А

| Требование | Где реализовано | Чем проверено |
|---|---|---|
| Модели через Pydantic | `SubmissionIn`, `DeclarationIn`, `SubmissionOut` (strict, `extra="forbid"`, frozen) | `test_dto_is_frozen_and_strict` |
| Независимый сервис приёма | `services/intake.SubmissionService` знает только порт репозитория | `test_service_is_independent_from_adapter` |
| Тестовый адаптер до появления HTTP | `SubmissionApi.post_submission / get_submission` - `ApiResponse(status, body)` | `test_post_*`, `test_get_submission_*` |
| Преобразование входной модели в доменный объект | `SubmissionIn.to_domain()`, обратно - `SubmissionOut.from_domain()` | `test_dto_to_domain_matches_domain_parser` (12 сдач) |
| HTTP-статусы не определяют доменные исключения | `STATUS_BY_CODE` только в адаптере; `ValidationError` - `SubmissionError` в `to_submission_error` | `test_domain_errors_know_nothing_about_http`, `test_pydantic_path_gives_same_domain_errors` |
| Репозиторий in-memory | `InMemorySubmissionRepository` | - |

### Общие требования этапа Б

| Требование | Где реализовано | Чем проверено |
|---|---|---|
| `Analyzer.analyze(submission, context) -> AnalysisReport` | `domain/analysis.py` (Protocol) | mypy strict, контрактные тесты |
| Context передаёт Assignment и доступ к данным через интерфейс | `AnalysisContext(assignment, …, submissions: SubmissionLookup)` | `test_end_to_end` |
| `analyzer_id`, `analyzer_version` в отчёте | `AnalysisReport`, `make_report` | `test_analyzer_contract`, `test_report_from_other_analyzer_is_rejected` |
| `LengthAnalyzer`: непустые строки, `rubric_feedback`, `score=null` | `adapters/analyzers.py` | `test_length_analyzer_counts_and_has_no_score` |
| `TemplateAnalyzer`: точные строки шаблона, `similarity`, пояснение «разрешено» | `adapters/analyzers.py` | `test_template_ranges` (5 случаев), `test_template_analyzer_reports_allowed_match` |
| Номера строк evidence - по исходному содержимому | `nonempty_line_numbers`, `template_ranges` | `test_nonempty_lines_use_original_numbering`, `test_validate_report_rejects` |
| JSONL и in-memory источники | `adapters/sources.py` | `test_sources.py` |
| Один набор контрактных тестов для обоих источников и обоих анализаторов | параметризованные фикстуры | `test_source_*` ×2, `test_analyzer_contract` ×24 |
| Сервис выбирает анализатор по реестру, без ветвлений по классам | `services/analysis.AnalysisService`, `AnalyzerRegistry` | `test_third_analyzer_without_changing_service` |

### Основной вариант Backend, этап Б

| Требование | Где реализовано | Чем проверено |
|---|---|---|
| Адаптеры источника и анализаторов вне сервиса приёма | `adapters/sources.py`, `adapters/analyzers.py`; сервис видит только порты `services/ports.py` | структура пакета, mypy |
| В тесте реальный источник заменён in-memory реализацией | `app.import_from(InMemorySource([...]))` | `test_real_source_is_replaced_by_in_memory_in_test`, `test_jsonl_and_in_memory_give_same_result` |
| Конфигурация приложения собирает зависимости | `app.build_application(assignments, config=AppConfig(...), extra_analyzers=...)` | `test_config_values_reach_report_config_hash`, `test_third_analyzer_is_connected_by_config_only` |
| Глобальное изменяемое состояние не является контейнером проекта | реестр и репозиторий создаются на каждый вызов; `BUILTIN_ANALYZERS` - `MappingProxyType` | `test_each_application_is_independent` |

### Обязательные проверки из задания

| Сценарий | Тест |
|---|---|
| Валидный импорт | `test_import_valid_file`, `test_end_to_end` |
| Повреждённый JSON | `test_decode_json_rejects_bad_json`, `test_jsonl_broken_line_does_not_stop_reading`, `test_post_errors[{broken]` |
| Неверные типы | `version-bool`, `code-int`, `text-list`, `decl-str-bool`, `int-student` и др. - в обоих путях |
| Дубликат | `test_duplicate_returns_already_accepted_and_does_not_grow`, `test_post_accepted_then_duplicate` |
| Конфликт | `test_conflict_does_not_overwrite_original`, `test_post_conflict_does_not_overwrite` |
| Ошибка анализатора | `test_analyzer_error_becomes_analysis_failure_and_keeps_submission`, `test_defective_report_is_rejected` |
| Освобождение ресурса | `test_jsonl_closes_file_after_full_read / on_early_exit / on_consumer_error` |
| Диапазоны evidence | `test_validate_report_rejects[line-zero / end-beyond-source / start-after-end / …]` |
| Неизменность исходного объекта | `assert raw == before` в парсере и DTO; snapshot `asdict` в `test_analyzer_contract` и `test_end_to_end` |

## 2. Команды проверки

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest            
ruff check .               
mypy src   

python examples/defense_demo.py   
```

## 3. Измерения

`python scripts/measure.py 10000`. Время - лучшее из
3 запусков; память - пик `tracemalloc` в отдельном запуске (tracemalloc замедляет код в разы).

| Операция (N = 10 000 сдач) | Время, мс | Пик памяти, МБ |
|---|---:|---:|
| Импорт JSONL → сервис приёма | 508.1 | 8.10 |
| Импорт InMemory → сервис приёма | 374.0 | 6.68 |
| Только чтение JSONL построчно | 80.4 | **0.06** |
| Только чтение файла целиком в список | 14.7 | **19.75** |

| Путь валидации | Всего, мс | На запись, мкс |
|---|---:|---:|
| Домен: `parse_submission(dict)` | 64.6 | 6.5 |
| Pydantic: `model_validate(dict)` + `to_domain()` | 68.1 | 6.8 |
| API-адаптер: `post_submission(JSON-строка)` целиком | 312.4 | 31.2 |

| Анализатор | Всего, мс | На сдачу, мкс |
|---|---:|---:|
| `LengthAnalyzer` | 709.2 | 70.9 |
| `TemplateAnalyzer` | 626.6 | 62.7 |

`slots=True` для 10 000 `Submission`: **1.69 МБ против 2.08 МБ** без slots (−18%).

### Условия измерений

- **CPU**: AMD Ryzen 5 5500U (6 ядер, 12 потоков, 2.1-4.0 ГГц)
- **RAM**: 14 GB
- **ОС**: Ubuntu 22.04.5 LTS (Jammy Jellyfish)
- **Python**: 3.12.15

**Выводы.**
1. **Pydantic не замедлил приём:** строгая DTO-валидация с преобразованием в домен стоит **6.8 мкс на запись против 6.5 мкс** у ручного парсера. 

2. **Полный API-запрос - 31 мкс**, из них на валидацию приходится 6.8 мкс. Остальное - строгий разбор JSON и SHA-256 сдачи для проверки duplicate/ conflict. Это цена строгого контракта и неизменности, а не Pydantic.

3. **Построчный JSONL-источник** держит в памяти одну строку: пик **0.06 МБ против 19.75 МБ** при чтении целиком. **Пик полного импорта** (8.10 МБ для JSONL, 6.68 МБ для InMemory) - это уже in-memory репозиторий с принятыми сдачами.

4. **Импорт из InMemory быстрее JSONL** (**374 vs 508 мс**): нет чтения диска. `deepcopy` каждой записи замедляет InMemory, но всё равно быстрее, чем чтение с диска.

5. **Анализаторы:** профилирование (`cProfile`) показало, что значительная часть времени - хеши сдачи и конфигурации (`asdict` + SHA-256) при создании отчёта и при его проверке на границе. Можно просто кешировать хеш принятой сдачи.
