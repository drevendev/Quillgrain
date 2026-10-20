# Existing tools remain owners of their behavior

The engine exports context, not consumer installation. Task facts, canon, character
identity, UI format, publication and distribution stay with the requesting project.
A style example is never evidence for a factual claim or a first-person experience.

ChatGPT receives `VOICE_CONTEXT.md` and `context.json` beside a separate brief.
Codex receives the same data and a generic `.agents/skills/quillgrain/SKILL.md`,
following the [official skill format](https://learn.chatgpt.com/docs/build-skills).
Copy an export into a consumer only under that consumer's explicit authorization.
No global Codex configuration is modified. The exported skill contains no private data.

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
