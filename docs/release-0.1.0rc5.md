# Реализация и проверка Quillgrain 0.1.0rc5

Версия реализует [спецификацию следующего релиза](next-version-spec-ru.md)
поверх сохранённой текущей работы и актуальной основной ветки с PR #26.
Исходная рабочая папка с незакоммиченными изменениями не изменяется:
реализация выполнена в отдельном worktree. Техническая готовность пакета
и фактическая проверка поведения в агенте учитываются отдельно.

| Задачи | Реализация | Проверка |
| --- | --- | --- |
| #34–35 | Общий host/lock/permissions контракт, согласованные имена, валидация staging дерева | Оба export/install пути, запрещённые host, tamper, имена, ресурсы и отказ до публикации |
| #36 | Общий `quillgrain`, связанные имена и metadata, диагностика известных совпадений | Два синтетических профиля сохраняются; реальный user/project selection — NOT_RUN |
| #37 | Общий stdlib verifier в engine и portable skill | Изолированный `python -I -S`, перенос, v1/v2 lineage и отрицательные векторы |
| #32–33, #39 | Целевая редактура в source skill, покрытия и opt-in editorial-review/v1 | Сохранение check-report/v1, scopes, воспроизводимость списка и отказ при output collision |
| #38 | Версионированные сценарии и отдельные критерии routing/mechanics/prose | Частичный Codex smoke; Claude Code не прошёл авторизацию. См. [подробности](agent-evaluation.md) |
| #40 | Оригинальные пары вмешательства/сохранения и компактный протокол | Материал готов; поведенческая польза правила NOT_RUN |
| #27–28 | Бюджет source-once, пять кнопок, два комментария, история для чтения | Python/Node/DOM: reload, импорт, клавиатура, двойной commit, остановка, неизменность принятых голосов |
| #29 | Partial-report/v2, provenance и срезы с n, UNKNOWN satisfaction, отдельные private notes | Счёт из raw votes, дубликаты комментариев, draft exclusion, сохранность входа |
| #30–31 | Quick-v2 контракты и проверяемый план самостоятельных сцен | Прямое происхождение, отсутствие фиктивного ORIGINAL, word budget, квоты и разделение материала |

Текущий автоматический набор использует оригинальные синтетические fixtures.
Локальная проверка на Python 3.14: 201 passed, 2 Windows symlink skips;
отдельный Node-набор: 8 passed. DOM integration tests выполнены для quick-v1
и quick-v2. Wheel/sdist собраны, установленный wheel прошёл export/verify/check
smoke; аудит исходников и обоих архивов проверил 336 членов, включая поиск
приватных контрольных строк.
Сборка и публичный аудит выполняются по фактическим wheel/sdist; счётчики
и результаты относятся к проверенному head и приводятся в описании ПР.
CI запускает quick-клиент через Python integration tests с фиксированными
jsdom-зависимостями из `tests/browser/package-lock.json`; обычные Node-клиенты
проверяются отдельно. Модельных вызовов из CI нет.

Полная live-приёмка Codex/Claude и визуальная проверка в обычном браузере
не объявляются пройденными. Codex CLI прочитал нужный skill, но вложенная среда
запретила helper/write операции. Claude Code сообщил об истёкшей OAuth-сессии.
Встроенный браузер не смог подключиться к локальному серверу; DOM-проверки
выполнены, а визуальная приёмка desktop/mobile остаётся NOT_RUN.

Релиз не публикует сайт, не запускает новый реальный Ink Duel, не изменяет
персональные skills и не подтверждает качество конкретного авторского голоса.
Вопросы литературной пользы проверяются после фиксации кандидата на отдельно
разрешённом новом материале.

## Integration of the profile recipe builder

PR #41 is incorporated before this release. Multi-register profile bundles now
load the same portable context/host/lock invariants as ordinary skills; their
wrapper adds only mode, file-manifest and rules-only checks. The bundled runtime
and engine use identical source bytes, including under isolated Python (-I -S).
The counter also plans feasible next-part intervals. Both the standalone helper
and qg length return failure for an infeasible interval without generating prose.
The combined Python suite passes 201 tests with two Windows symlink skips; Node
passes eight tests and quick-v1/v2 integration passes with pinned jsdom 26.1.0.
