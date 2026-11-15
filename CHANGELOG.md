# Changelog

## Unreleased — source-once Ink Duel and explicit length budgets

Add a separately versioned quick plan/session/client with a fixed default budget,
normalized-source deduplication and balanced sides. Five ordinal preference choices,
two optional card comments, draft persistence, protected commit/import and explicit
stop/review replace the longer rubric only for new-format campaigns. Read-only
partial reports support quick-v1 and historical numeric-v1/pair-v2/multi-v3 without
inferring an overall vote from old criteria or publishing a win-rate league.
Add the portable `qg-words/v1` counter with per-part and aggregate checks; skills
ship the identical helper. None of these commands generate model responses.

## Unreleased — Claude and Codex writing skills

The current assistant writes with Quillgrain voice context without a local model
or separate API. Adds the Claude export target, explicit project/portable skill
installation, host/lock verification, shared writing instructions, and Codex UI
metadata. Bound skills carry their context and lock so they survive relocation.
Generic installs contain no voice data; existing host permissions are preserved.

## Unreleased — local IO repairs

Apply duplicate-key and nonfinite-value rejection to corpus selection JSONL as
well as JSON. Remove transaction-owned bundle staging after handled write or
publication failures, preserving existing destinations and the original error.

## 0.1.0rc4 — versioned private corpus resources

Adds private corpus/source/fragment schemas, explicit storage approval, immutable
content objects, pinned voice v2 references and context/lock v2 lineage. Local
metadata search, impact and explanation commands support source maintenance.
Rules-only builds need no corpus; requested unavailable examples fail explicitly.
Source and example host permissions intersect; protected work groups and known
duplicates cannot enter examples. Voice/context v1 remains supported.
Synthetic tests cover integrity, scope, permissions, missing resources, revocation,
path/junction boundaries, offline exports and caller-selected example pools.

## Unreleased — pairwise Ink Duel v2

Separate thirty-round categorical protocol with five categories, six treatment
pairs per category, counterbalanced sides, a two-text one-page client and partial
JSON progress. Optional independent identity guesses and author resemblance stay
separate from quality. Exact duplicate prose cannot produce exclusive wins or
recognition credit. Neutral meaning slots replace prescriptive anchors for the
new protocol. Legacy numeric campaigns remain unchanged. A synthetic UI demo is
provided; a new real-source campaign and inference run are separate work.

## 0.1.0rc3

Russian local Ink Duel: frozen twenty-case blind sessions, two-stage ratings,
browser save/import/export, separate reveal and descriptive reports. No real
sources or outputs ship with the engine; tests contain original synthetic data.

Recheck trusted source permissions and allowlists before every read. Exclude
multiline HTML comments and lazy blockquotes from narration. Reject output links,
publish bundles only to new directories, and replace regular files atomically.
Validate scoped mandatory conflicts, fixed-policy budgets and raw evaluation
evidence before producing a new review set.

## 0.1.0rc2

Trusted source-root configuration can restrict inventory to an explicit `include_files`
allowlist. Unselected neighbouring notes are never opened. Empty lists read no files.

## 0.1.0rc1

Portable data contracts; explicit local composition and locks; read-only corpus intake;
Markdown/JSON/Codex/legacy exports; scoped deterministic checks; optional external
Scriptorium bridge/import; candidate feedback and evaluation evidence records.
Original synthetic fixtures only. Human voice validation is a separate decision.
