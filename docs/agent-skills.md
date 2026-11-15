# Quillgrain как навык для Claude и Codex

Текст пишет модель текущего чата: Claude в Claude или модель Codex в Codex.
Quillgrain собирает профиль голоса из правил и выбранных примеров, передаёт его
ассистенту и проверяет готовый текст. Qwen, Ollama и отдельный API для этого не нужны.
Локальные модельные прогоны Ink Duel — отдельный способ испытывать профили.

## Установка общего навыка

Установите Python-пакет движка в выбранное окружение:

```text
python -m pip install -e PATH_TO_QUILLGRAIN_ENGINE
qg skill install --agent codex --project PATH_TO_WRITING_PROJECT
qg skill install --agent claude --project PATH_TO_WRITING_PROJECT
```

Если `qg` не находится в PATH, используйте `python -m quillgrain` из этого окружения.
Команды создают соответственно `.agents/skills/quillgrain/` и
`.claude/skills/quillgrain/` внутри указанного проекта. Существующий навык не
перезаписывается. Для новой версии выберите новую папку или явно управляйте старой
копией самостоятельно. Личные настройки и другие проекты не меняются.

Откройте новую сессию в проекте и вызовите:

```text
Codex: $quillgrain Отредактируй этот текст с выбранным профилем. Факты сохрани.
Claude Code: /quillgrain Напиши статью по этому brief, используя выбранный профиль.
```

Передайте путь к готовому контексту либо выбранному voice pack. При совпадении
задачи с описанием навык также доступен для автоматического выбора ассистентом.
Общий навык не содержит личного корпуса или профиля Dreven; он умеет использовать
предоставленный профиль и собирать контекст через `qg`.

## Навык со встроенным голосом

Соберите отдельный контекст для нужного ассистента. В примере ниже используется
публичная синтетическая фикстура движка, а не персональный голос:

```text
qg pack build --pack examples/synthetic/common --register essay --language ru --target codex --out out/codex-voice
qg pack build --pack examples/synthetic/common --register essay --language ru --target claude --out out/claude-voice
```

В каждом экспорте уже есть полная папка навыка с выбранным контекстом. Для установки
в другой проект можно скопировать эту папку целиком либо выполнить:

```text
qg skill install --agent codex --bundle out/codex-voice --project PATH_TO_WRITING_PROJECT
qg skill install --agent claude --bundle out/claude-voice --project PATH_TO_WRITING_PROJECT
```

Установка проверяет контекст, его host и lock, затем создаёт навык из поставляемых
инструкций и проверенных данных. Соседние файлы экспорта не устанавливаются.
`references/context.json`, `references/VOICE_CONTEXT.md` и
`references/quillgrain.lock.json` перемещаются вместе с навыком. Оригинальная папка
экспорта и исходный корпус после этого для письма не нужны. Для новой сборки или
смены языка/регистра нужен исходный pack и его зависимости.

Персональный voice pack выбирается через `--pack`; родители — через
`--bind ID=PATH`, корпус — через `--corpus-bind ID=PATH`. Приватные сборки храните
вне публичного checkout. Доступ для `codex` не означает доступ для `claude`:
каждый пакет и выбранный источник должны разрешать фактический host. Движок не
расширяет разрешения автоматически и не отправляет данные при сборке.

## Переносимый навык и Claude в браузере

Для самостоятельной папки вместо установки в проект используйте `--out`:

```text
qg skill install --agent claude --bundle out/claude-voice --out out/quillgrain
```

Получится стандартная папка `quillgrain/` с `SKILL.md` и ресурсами. Её можно
перенести в поддерживаемое локальное расположение навыков. Для интерфейса,
принимающего ZIP навыка, упакуйте папку так, чтобы в архиве был
`quillgrain/SKILL.md`. Например, в PowerShell:

```powershell
Compress-Archive -Path out/quillgrain -DestinationPath out/quillgrain.zip
```

Установка в `.claude/skills` относится к **Claude Code**. Она не загружает навык
в аккаунт claude.ai и не устанавливает его в обычный браузерный чат. Доступность
загрузки и исполнения ресурсов зависит от выбранного интерфейса. Если там нет
движка `qg`, ассистент может писать по встроенному контексту, но обязан обозначить,
что проверка digest и программные проверки не выполнены.

## Проверка результата

```text
qg context verify --context CONTEXT_JSON --host codex --lock LOCK_JSON
qg check --draft DRAFT_FILE --context CONTEXT_JSON --out NEW_CHECK_JSON
```

В Claude замените host на `claude`. Сначала ассистент проверяет контекст, затем
пишет текст сам и проверяет полученный файл. Факты, канон и личный опыт берутся
из задания, а примеры задают только письмо. Техническая проверка не доказывает
качество или сходство с автором; окончательное решение остаётся за человеком.

Форматы и пути сверены с официальной документацией
[Codex](https://learn.chatgpt.com/docs/build-skills) и
[Claude Code](https://code.claude.com/docs/en/skills).
