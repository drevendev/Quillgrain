# Quillgrain

**Every voice has a grain.**

Write and edit with an author voice in **Claude or Codex**. The assistant in your
current session writes the text; Quillgrain supplies versioned voice rules,
selected examples, and deterministic draft checks. Install it as an agent skill,
or export a self-contained skill with a selected voice. No Qwen, Ollama, separate
model call, or API key is needed for the skill workflow. Python 3.11+ for the engine.

Install the reusable skill into a writing project after installing the engine:

```text
qg skill install --agent codex --project PATH_TO_WRITING_PROJECT
qg skill install --agent claude --project PATH_TO_WRITING_PROJECT
```

Invoke `$quillgrain` in Codex or `/quillgrain` in Claude Code, followed by your task
and chosen context or pack. See the [agent skill guide](docs/agent-skills.md) for
voice-bound skills, portable folders, and the distinction from Claude web chat.
The engine itself requires no account, model server, telemetry, or private voice.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\qg.exe doctor
.\.venv\Scripts\qg.exe pack validate --pack examples/synthetic/common
.\.venv\Scripts\qg.exe pack build --pack examples/synthetic/common --register essay --public --out out/demo
.\.venv\Scripts\qg.exe check --draft examples/synthetic/draft.md --context out/demo/context.json --out out/check.json
.\.venv\Scripts\python.exe -m pytest
```

On POSIX use `.venv/bin/python` and `.venv/bin/qg`. The synthetic demo is original
AI-prepared data, not an empirical human corpus. It checks a fictional lamp brief;
the fixture's forbidden-literal constraint is specific to that brief.

For the independent neutral pack, clone
[Quillgrain_Voice_Common](https://github.com/drevendev/Quillgrain_Voice_Common) next to this
repository and pass `--pack ../Quillgrain_Voice_Common`. Common contains soft editorial
defaults and RU/EN examples. Other voices are data packs, not engine forks.

Exports contain `VOICE_CONTEXT.md`, `context.json` and a version/digest lock.
`--target patchpitch` adds a portable `voice-bundle.json` for explicit local
application import; see the [consumer contract](docs/consumer-voice.md).
`--target codex` additionally exports `.agents/skills/quillgrain-<voice-slug>/`;
`--target claude` exports `.claude/skills/quillgrain-<voice-slug>/`. For the synthetic
pack the name is `quillgrain-synthetic`; `--skill-name NAME` selects another valid
name. Both include instructions,
CLI guidance, and pinned context/lock files under `references/`, so the skill folder
can be moved independently of the rest of the export. The bundled stdlib
`scripts/voice_context.py` verifies context/lock, host and permissions with Python
alone. Generic installs keep the name `quillgrain`. Standalone `--out` remains an
exact final path whose last component must match the selected skill name.
`--target patchpitch-legacy` exports a maximum 1,200-codepoint `voice_reference.txt`
and manifest for manual use in the existing field. Pass `--host` explicitly when
the actual model surface differs. `pack build` creates files without installing
integrations; `skill install` explicitly installs into the selected project or
new skill folder.

See [contracts and composition](docs/voice-pack-format.md),
[private intake](docs/corpus-intake.md), [privacy](docs/privacy.md),
[evaluation](docs/evaluation.md), and [integration boundaries](docs/integration-contracts.md).
Technical checks establish structural properties; human review determines voice
quality. Optional Scriptorium observations retain their native units and nulls.

Version 0.1.0rc5 supports explicitly bound private corpus repositories and voice v2
references, while retaining voice/context v1 compatibility. Approved sources can
live in a separate PRIVATE data repository with local checks and no CI. Builds pin
exact revisions/fragments; exports embed selected examples and work offline.
Use `--examples none` for an explicit rules-only build. See the
[corpus repository contract](docs/corpus-repository.md) for intake, permissions,
metadata search, impact reports and `qg explain`.

[Ink Duel](docs/ink-duel.md) is a separate local editorial evaluation workflow.
The [quick format](docs/ink-duel-quick.md) freezes a source-once budget (default 30),
uses five preference buttons and two optional comments, and supports stopped partial
review without rewriting old campaigns. No model is invoked by these commands.
Its model runner is optional and does not determine which model writes with the
skill. Real case packs, private references, votes and keys stay outside the repository.

For explicit word budgets use `qg length --input DRAFT --min-words MIN --max-words MAX`.
Repeat `--input` for parts and optionally `--part-range MIN:MAX` once per part;
the sum is also checked against the overall range. Exit 1 reports a length miss.
The same stdlib counter ships in portable skills; it never invokes an editor/model.

For local editorial review, `qg check --review-json NEW_JSON --review-md NEW_MD`
exports the applied human-review rules with context/draft digests and NOT_REVIEWED
states. The ordinary check-report/v1 is unchanged; CLI coverage distinguishes
executed, human-review and unavailable-character checks. See
[editorial review](docs/editorial-review.md) and [bounded editing](docs/agent-skills.md).

The [fiction protocol](docs/ink-duel-fiction.md) adds explicit task provenance,
rights receipts, fact packs, word budgets, previous-profile controls and
reference/development/reserve separation. New scenes have no fabricated ORIGINAL.
Reports preserve ordinal votes and leave absolute satisfaction unknown.
[Agent acceptance](docs/agent-evaluation.md) and
[intervene-or-preserve regression](docs/editorial-regression.md) are separate from
Ink Duel. See the [rc5 implementation and validation record](docs/release-0.1.0rc5.md)
for the actual scope of verification, including unavailable live-agent checks.
