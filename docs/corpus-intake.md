# Read-only private intake

`qg corpus inventory --config source-roots.local.json --out inventory.json` accepts
trusted local configuration with a `roots` array. Each entry declares `alias`, an
absolute `path`, `source_kind`, `language`, `register`, `rights`, `permissions`, and
`approval: {by, basis}`. `authorship` defaults to unknown. Optional `max_files` bounds
the initial inventory; `include_files` limits a root to named relative files (an empty
list reads none); `work_groups` explicitly maps relative locators to work IDs.
Never commit this configuration or the inventory.

Permissions explicitly declare `local_analysis`, `retrieval`, `private_git_excerpt`,
`approved_model_hosts`, and `public_redistribution`. Missing grants are not true.
Start with a small diverse selection, inspect provenance and authorship, and split
whole works/duplicate groups before tuning. Unknown or AI-assisted writing cannot
become a human reference merely because it lives in the vault. Generated approved
examples keep their generated origin. Mark collaborative editorial history honestly.

Inventory reads UTF-8 Markdown/plain text, handles BOM/CRLF/NFC, excludes hidden and
attachment/plugin/secret directories, and never expands links. The conservative
narration extractor removes frontmatter, fenced/inline code, marked quotes, embeds
and dash-led dialogue. It retains source-line ranges plus raw/extracted SHA-256.
Unmarked copied prose and unnamed speakers require human review; the parser cannot
establish authorship. Group versions explicitly when filenames are ambiguous.

Copy chosen corpus-item records to `selection.jsonl` with candidate/reference/
holdout/excluded selection. Then run:

```text
qg corpus prepare --selection selection.jsonl --config source-roots.local.json --out prepared
```

Alternatively set `QUILLGRAIN_PRIVATE_HOME` to a private local directory containing
`config/source-roots.local.json`. Prepare rechecks source hashes, extraction version,
permissions, path boundaries and split leakage before writing derived files. Outputs
inside a source root are denied. Symlink/junction escapes are rejected after path
resolution. As with ordinary local file IO, a hostile concurrent filesystem mutation
is outside the v0.1 threat model; use trusted roots and a stable read-only snapshot.

`feedback record` stores before/after, hashes, reason and scope in the chosen private
output. It activates no rules. Fact corrections and one-off changes cannot propose
a voice rule through that command. Owner decisions remain separate.

## Изменение извлечения в 0.1.0rc3

`qg-narration-nfc-v2` исключает многострочные HTML-комментарии и продолженные
blockquote до границы блока. Незакрытые/неоднозначные блоки консервативно исключаются.
Прежние манифесты v1 не переинтерпретируются: их нужно явно пересобрать из неизменённых
источников. Разбор Markdown и статус authored не доказывают авторство.

Разрешение и точный allowlist повторно проверяются непосредственно перед каждым
чтением. Пустой allowlist разрешает ноль файлов. Подготовка создаёт новый каталог;
занятый путь, symlink/reparse и запись в исходники отклоняются. Неудачная транзакция
может оставить каталог `.qg-incomplete-*`, который не является готовым результатом.
Это локальная транзакция одного оператора, не защита от злонамеренной конкурентной
подмены дерева файлов.
