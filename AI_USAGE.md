# Использование ИИ в ЛР 1

## Инструмент

Claude (Anthropic).

## Для чего использовался

### Изучение и разбор задания
- Разбор требований к этапам А и Б: схема полей, форматы `submissions.jsonl`, `invalid_submissions.jsonl`, `assignments.json`.
- Объяснение концепций: `Protocol`, `MappingProxyType`, Pydantic + домен, реестр фабрик, `AnalysisContext`, `config_hash`, `submission_hash`.
- Ответы на вопросы по архитектуре (слои domain/services/adapters, порты, адаптеры).

### Генерация тестов и скрипта
- **Тесты** (`tests/test_*.py`) **сгенерированы** с **помощью** **ИИ** на основе описанных мной требований и сценариев.
- Параметризованные тесты на общий контракт источников и анализаторов.
- Тесты на ошибки валидации, дубликат/конфликт, закрытие файла, подмену источника in-memory.
- скрипт измерений `scripts/measure.py`

## Что сделано самостоятельно

- **Архитектура** пакета: разделение на `domain/`, `services/`, `adapters/`, `app.py`, `cli.py`.
- **Все** **модули** **кода**: `models.py`, `errors.py`, `validation.py`, `hashing.py`, `analysis.py`, `ports.py`, `intake.py`, `services/analysis.py`, `sources.py`, `memory.py`, `api.py`, `analyzers.py`, `declaration.py`, `app.py`, `cli.py`.
- **Данные** `data/*.jsonl`, `data/assignments.json` - (**синтетические**, **на** **основе** **примеров** **из** **задания**).
