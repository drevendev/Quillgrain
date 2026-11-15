# Existing tools remain owners of their behavior

Pack builds export context. Explicit `qg skill install` installs an agent skill only
into the caller-selected project or new directory. Task facts, canon, character
identity, UI format, publication and distribution stay with the requesting project.
A style example is never evidence for a factual claim or a first-person experience.

ChatGPT receives `VOICE_CONTEXT.md` and `context.json` beside a separate brief.
Codex receives `.agents/skills/quillgrain/`; Claude Code receives
`.claude/skills/quillgrain/`. These share portable `SKILL.md` instructions following
the [Codex format](https://learn.chatgpt.com/docs/build-skills) and
[Claude format](https://code.claude.com/docs/en/skills). The current assistant writes
and edits; the skill does not invoke a local model or require an API key.

A generic installation contains only instructions, CLI guidance, and Codex UI
metadata. A voice-bound export or installation additionally embeds the verified
context, readable Markdown, and lock under `references/`. Those derived files can
contain private data and retain the context's visibility and host restrictions.
Copy the whole skill directory to move it independently of its original export.
Supplied bundle code and unverified Markdown are never copied by the installer.

`qg context verify --context FILE --host ACTUAL_HOST --lock LOCK` checks context
integrity, retrieval/host permissions, and lock digest before use. Bound installation
requires the chosen agent to match the recorded host. The `claude` target defaults
to host `claude`; it does not add Claude to existing pack/source allowlists. Existing
private approvals are preserved. No global configuration is modified. See the
[installation guide](agent-skills.md) for commands and surface limitations.

The legacy announcement adapter supplies `voice_reference.txt` (Python `len()` <=
1,200) plus a digest/visibility manifest. This measures Unicode codepoints, not UTF-8
bytes, graphemes or tokens. Record the actual preset (Warm/Clear/Lively) and language
when testing; a preset can interact with the voice pack. Existing application prompts
may require English, so an unsupported author language needs a separately marked
adaptation, not a silent claim that the pack supports it.

## Optional Scriptorium bridge

Use a separate, trusted, pinned Git checkout and interpreter:

```text
qg analyze --input prepared.txt --checkout PATH --python PYTHON --revision COMMIT --out observations.json
qg analyze --input prepared.txt --import observations.json --out imported.json
```

The bridge imports `analyze_deterministic_metrics` from that external checkout in an
isolated Python process. It verifies HEAD and a clean worktree; no analyzer is vendored.
Import checks the input hash and exact native schema/profiles. The wrapper preserves
native dictionaries, units and nulls. `mean_sentence_length_chars` is characters per
sentence. Missing vocabulary dictionaries do not become zero. Without a checkout,
analyze writes `METRICS_NOT_RUN`; `--require-provider` additionally exits 4. Compilation
and metric import do not require an installed backend. Provider exceptions are explicit.

Core targets Python 3.11+. A provider's runtime/license/packaging remains its owner's
responsibility. Check a specific revision/runtime; do not assume compatibility from
another project's documentation. Short input is diagnostic, never author calibration.
