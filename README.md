# Quillgrain

**Every voice has a grain.**

Compile a versioned, permission-aware writing context, export it for an existing
writing tool, and check a draft without changing it. Python 3.11+. No account,
model server, API key, telemetry, database or private voice is required.

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
[Quillgrain_Common](https://github.com/drevendev/Quillgrain_Common) next to this
repository and pass `--pack ../Quillgrain_Common`. Common contains soft editorial
defaults and RU/EN examples. Other voices are data packs, not engine forks.

Exports contain `VOICE_CONTEXT.md`, `context.json` and a version/digest lock.
`--target codex` additionally exports a generic `.agents/skills/quillgrain/SKILL.md`.
`--target patchpitch-legacy` exports a maximum 1,200-codepoint `voice_reference.txt`
and manifest for manual use in the existing field. Pass `--host` explicitly when
the actual model surface differs. Exports do not install consumer integrations.

See [contracts and composition](docs/voice-pack-format.md),
[private intake](docs/corpus-intake.md), [privacy](docs/privacy.md),
[evaluation](docs/evaluation.md), and [integration boundaries](docs/integration-contracts.md).
Technical checks establish structural properties; human review determines voice
quality. Optional Scriptorium observations retain their native units and nulls.
