# Day22

`Day22` — это набор скриптов для оценки качества RAG-пайплайна, построенного на артефактах из `../Day21`.

Проект решает три задачи:

- сравнивает ответ модели без контекста и ответ с RAG на одном вопросе;
- генерирует контрольные вопросы по выбранным документам из базы `Day21`;
- прогоняет набор вопросов в режимах `without RAG` и `with RAG`, после чего собирает HTML-отчёт.

## Как устроен проект

Источник данных и retrieval берутся из соседнего каталога `../Day21`:

- FAISS-индексы: `../Day21/output/*.faiss`
- metadata с чанками: `../Day21/output/*_chunks.json`
- исходные документы: `../Day21/documents`

Генерация ответов выполняется через один из двух бэкендов:

- `assistant` — HTTP-сервис из `../LLM Assistant`
- `ollama` — локальный Ollama

## Файлы в репозитории

- `rag_compare.py` — сравнение обычного ответа и ответа с RAG для одного вопроса, с возможностью показать этапы retrieval и отключать отдельные стадии поиска
- `generate_questions_from_sources.py` — генерация контрольных вопросов по выбранным файлам из `Day21`
- `build_eval_report.py` — массовый прогон контрольных вопросов и сборка HTML-отчёта
- `compare_single_question_rag.py` — отладочное сравнение двух RAG-веток на одном вопросе
- `compare_topk_search_modes.py` — запуск `rag_compare.py` в трёх режимах retrieval и сравнение итогового `top-k`
- `llm_backends.py` — единая обвязка для `LLM Assistant` и `Ollama`
- `generated_control_questions.json` — пример сгенерированного набора вопросов
- `rag_quality_report.html` — пример готового HTML-отчёта

## Зависимости

Минимально нужны:

- Python 3.10+
- `faiss-cpu`
- `numpy`
- запущенный `Ollama` для retrieval-эмбеддингов
- запущенный `LLM Assistant`, если используется `--llm-backend assistant`

Пример установки Python-зависимостей:

```bash
pip install faiss-cpu numpy
```

## Важное про embedding-модель

Retrieval должен использовать ту же embedding-модель, которой был построен индекс в `Day21`.

По коду здесь значение по умолчанию для retrieval — `bge-m3`. Если индекс в `../Day21/output` был построен другой моделью, обязательно передайте её явно через `--embed-model`, иначе поиск по чанкам будет некорректным.

## Быстрый старт

### 1. Сравнить обычный ответ и ответ с RAG

```bash
python rag_compare.py "Какие требования описаны в документации?" --embed-model bge-m3
```

По умолчанию скрипт:

- берёт индекс `../Day21/output/structure.faiss`
- берёт чанки `../Day21/output/structure_chunks.json`
- ищет `top-k=5` чанков
- обращается к `LLM Assistant` по `http://127.0.0.1:8000`
- использует модель `openai/gpt-4o-mini`

Полезные параметры:

- `--strategy fixed|structure`
- `--index-file <path>`
- `--metadata-file <path>`
- `--embed-model <model>`
- `--assistant-url <url>`
- `--assistant-model <model>`
- `--auth-token <token>`
- `--show-retrieval-stages` — показать все этапы retrieval
- `--disable-dense-search` — отключить dense embedding search
- `--disable-lexical-rerank` — отключить lexical boost для dense-кандидатов
- `--disable-lexical-fallback` — отключить keyword fallback по всем чанкам
- `--retrieval-only` — выполнить только retrieval и не вызывать LLM

### 1.1. Посмотреть этапы retrieval

```bash
python rag_compare.py "Как включить сервисный режим контроллера Sigur?" --show-retrieval-stages --retrieval-only
```

В этом режиме скрипт печатает:

- `Query variants`
- `Embedding queries`
- кандидатов после `Dense stage`
- кандидатов `After lexical rerank`
- кандидатов `Lexical fallback`
- финальный `top-k`

### 1.2. Сравнить top-k для трёх режимов поиска

```bash
python compare_topk_search_modes.py "Как включить сервисный режим контроллера Sigur?"
```

Скрипт запускает `rag_compare.py` в трёх конфигурациях:

- всё включено
- выключен `lexical-rerank`
- выключен `lexical-fallback`

Если нужен подробный вывод по каждому режиму, можно добавить:

```bash
python compare_topk_search_modes.py "Как включить сервисный режим контроллера Sigur?" --show-retrieval-stages
```

### 2. Сгенерировать контрольные вопросы по документам

Список файлов можно передать через `files.txt` или параметрами `--source-file`.

Пример:

```bash
python generate_questions_from_sources.py --file files.txt --output-file generated_control_questions.json
```

Что делает скрипт:

- читает список выбранных файлов из `Day21/documents`
- подбирает связанные чанки из `structure_chunks.json`
- отправляет материал в LLM
- сохраняет JSON с вопросами, ожидаемыми фактами и группами ключевых слов для грубой автоматической оценки

Полезные параметры:

- `--file <txt|json>`
- `--source-file <filename>` можно указывать несколько раз
- `--question-count <n>`
- `--max-chunks-per-file <n>`
- `--max-total-chunks <n>`
- `--llm-backend assistant|ollama`
- `--output-file <path>`

### 3. Построить итоговый отчёт по качеству RAG

```bash
python build_eval_report.py --questions-file generated_control_questions.json --report-file rag_quality_report.html --embed-model bge-m3
```

Скрипт:

- загружает контрольные вопросы из JSON
- для каждого вопроса получает ответ без RAG
- для каждого вопроса получает ответ с RAG
- оценивает ответы по `keyword_groups`
- проверяет, были ли извлечены ожидаемые источники
- собирает HTML-отчёт со сводной статистикой

Полезные параметры:

- `--questions-file <path>`
- `--report-file <path>`
- `--dry-run`
- `--top-k <n>`
- `--llm-backend assistant|ollama`
- `--assistant-model <model>`
- `--ollama-model <model>`

## Типовой workflow

1. В `Day21` подготовить документы, чанки и FAISS-индекс.
2. В `Day22/files.txt` перечислить документы, по которым нужно сделать контрольный набор.
3. Запустить `generate_questions_from_sources.py`.
4. Проверить JSON с вопросами и при необходимости подправить его вручную.
5. Запустить `build_eval_report.py`.
6. Открыть `rag_quality_report.html` и сравнить качество `with RAG` и `without RAG`.

## Отладка

Для точечной проверки одного вопроса есть дополнительный скрипт:

```bash
python compare_single_question_rag.py "Как включить сервисный режим контроллера Sigur?" --show-prompts
```

Он помогает понять:

- какие чанки выбрал retrieval
- как отличается prompt между двумя RAG-ветками
- как меняется итоговый ответ модели

Для анализа именно retrieval-части удобнее использовать:

```bash
python compare_topk_search_modes.py "Как включить сервисный режим контроллера Sigur?" --show-retrieval-stages
```

Этот запуск помогает увидеть, как меняется `top-k`, если отключить:

- `lexical-rerank`
- `lexical-fallback`

## Замечания

- Если `--auth-token` не передан и выбран `assistant`, код пытается зарегистрировать временного пользователя через `/auth/register`.
- `rag_compare.py` не позволит одновременно отключить и `dense search`, и `lexical fallback`, потому что тогда retrieval не сможет собрать кандидатов.
- При отсутствии файлов индекса или metadata скрипты ожидаемо падают с ошибкой: артефакты должны быть заранее собраны в `Day21`.
- В репозитории уже лежат примерные результаты: `generated_control_questions.json` и `rag_quality_report.html`.
