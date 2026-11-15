# Local Quillgrain commands

Use these commands when a context must be built, verified, or checked. `qg` is
installed with the Quillgrain Python package (`python -m pip install -e PATH_TO_ENGINE`).
If `qg` is not on PATH, use the selected environment's `python -m quillgrain`.
Use an existing installation; do not install dependencies merely to write from an
already supplied context. Quote all paths as required by the current shell.

## Build a selected voice

For Codex, use `--target codex`; for Claude, use `--target claude`. These default
to the matching `model_host`. A pack and every selected source must already allow
that host. Neither command sends data or calls a model.

```text
qg pack validate --pack PACK
qg pack build --pack PACK --language ru --register essay --target codex --out NEW_EXPORT
qg pack build --pack PACK --language ru --register essay --target claude --out OTHER_NEW_EXPORT
```

Choose the language and register for the real task. Use `--bind ID=PATH` for pinned
parent packs and `--corpus-bind ID=PATH` for explicitly selected corpus repositories.
Use `--tag TAG` for project or delivery layers; `--example-pool TAG` also requires
the same `--tag TAG`. Use `--examples none` only when rules-only output is intended.
Missing resources or denied hosts require a truthful explanation, not broader
permissions or an invented profile. Keep private exports outside public checkouts.

## Verify and check

```text
qg context verify --context CONTEXT_JSON --host codex --lock LOCK_JSON
qg check --draft DRAFT_FILE --context CONTEXT_JSON --out NEW_CHECK_JSON
```

Use `--host claude` in Claude. For named dialogue, pass the consumer's actual
character spans with `qg check --scopes SCOPES_JSON`; do not invent offsets.
The checker leaves the draft unchanged. Read its findings, errors, and skipped
checks; exit 3 means a check failed. `human_review` checks need editorial judgment.
Without a lock, context verification checks the context digest and host but cannot
verify the separate lock. Checks measure structural constraints, not factual truth
or voice quality.

Record requested edits as candidate feedback:

```text
qg feedback record --before ORIGINAL_FILE --after EDITED_FILE --context CONTEXT_JSON --note NOTE_FILE --reason voice --out NEW_FEEDBACK_JSON
```

Choose the actual reason: `voice`, `fact`, `structure`, `taste`,
`project_constraint`, `one_off`, or `unknown`. This never activates new rules.
