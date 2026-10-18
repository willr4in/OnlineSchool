# OnlineSchool - ЛР 1 «Приём работ и расширяемые анализаторы»

Основа системы онлайн-школы: принимает сдачи лабораторных, валидирует их и запускает заменяемые анализаторы. Траектория  **Backend**, основной уровень.

## Установка и проверка

Нужен Python 3.12+.

```bash
cd school-lab
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest        
ruff check .
mypy src                
```

## Запуск

```bash
school-lab import data/submissions.jsonl            
school-lab import data/invalid_submissions.jsonl    
school-lab analyze data/submissions.jsonl --assignments data/assignments.json
school-lab analyze data/submissions.jsonl --assignments data/assignments.json --analyzer template

python examples/defense_demo.py     # сценарий защиты: 201 → 200 → 409, импорт с ошибками, третий анализатор
```

Коды завершения CLI: `0` - всё успешно, `1` - есть ошибки отдельных строк/анализов
(корректные записи при этом приняты), `2` - источник или файл заданий недоступен.

## Архитектура

```
src/school_lab/
  domain/                 чистый домен: нет Pydantic, HTTP, файлов, stdin
    models.py             
    errors.py             
    validation.py         
    hashing.py            
    analysis.py           
  services/               сценарии приложения
    ports.py              
    intake.py             
    analysis.py           
  adapters/               конкретные реализации и внешние интерфейсы
    api.py                
    memory.py             
    sources.py            
    analyzers.py          
    declaration.py        
  app.py                  AppConfig + build_application(): сборка зависимостей
  cli.py                  CLI-адаптер
```

Ключевые решения:

- **Два входа, одна политика.** CLI/импорт используют доменный `parse_submission`, API — Pydantic-DTO.
  Параметризованный тест прогоняет 25 ошибочных входов через оба пути и требует одинаковых `code` и `field`.
  Корректные 12 сдач в обоих путях дают равные `Submission`.
- **Идентификаторы.** Тот же `submission_id` + тот же хеш → `duplicate` (возвращается уже принятая сдача);
  другое содержимое → `conflict`, исходник не перезаписывается. Новая версия = новый `submission_id`.
- **Неизменность.** Доменные модели `frozen=True, slots=True`, DTO `frozen=True`; валидация не меняет вход;
  in-memory источник выдаёт копии.
- **Ресурс.** Файлом владеет контекст `JSONLSource.open()`; файл закрывается при полном чтении,
  `break` и исключении.
- **Evidence.** Номера строк — по исходному `text`/`code` (с 1, включительно). `TemplateAnalyzer`
  сравнивает блоки строк точно; пустой шаблон ни с чем не совпадает.
- **score = null.** Ни длина, ни совпадение с разрешённым шаблоном не являются оценкой качества.

### Конфигурация и третий анализатор

```python
app = build_application(assignments)                                   # length, template
app = build_application(assignments, extra_analyzers={"declaration": DeclarationAnalyzer})
app = build_application(assignments, config=AppConfig(config_version="2"))  # другой config_hash отчётов
```

`AnalysisService` выбирает анализатор по имени в реестре, поэтому для нового анализатора меняется только вызов build_application (добавляется extra_analyzers). AppConfig (config_version, mode) не меняется. `BUILTIN_ANALYZERS` - неизменяемая таблица (`MappingProxyType`), а реестр создаётся
заново для каждого приложения.

## Тесты

| Файл | Тестов | Что проверяет |
|---|---:|---|
| `test_validation.py` | 36 | доменный парсер: валидная запись, 25 ошибочных случаев, неизменность входа, строгий JSON, хеш |
| `test_api.py` | 50 | Pydantic DTO → домен; одинаковые ошибки двух путей; статусы 201/200/400/409/422/404 |
| `test_intake.py` | 10 | accepted / duplicate / conflict, отсутствие перезаписи, импорт после битой строки |
| `test_cli.py` | 3 | `import`: коды 0/1/2, номер строки для каждой строки `invalid_submissions.jsonl` |
| `test_sources.py` | 13 | **общий контракт** JSONL и in-memory; закрытие файла при `break`/исключении |
| `test_analyzers.py` | 57 | **общий контракт** обоих анализаторов на 12 сдачах; диапазоны evidence; отказ дефектных отчётов |
| `test_analysis_service.py` | 9 | реестр, ошибка анализатора, дефектный отчёт, новый анализатор без правки сервиса |
| `test_app.py` | 12 | сборка из конфигурации, **подмена источника in-memory**, независимость приложений, третий анализатор, сквозной сценарий, CLI `analyze` |
