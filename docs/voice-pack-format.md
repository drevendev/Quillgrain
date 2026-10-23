# Portable voice contracts

The canonical format is JSON. Closed Draft 2020-12 schemas ship in
`src/quillgrain/schemas/` and in the installed wheel. Regenerate them using
`python scripts/write_schemas.py`. Unknown fields and schema versions are rejected.
`voice.json` contains inline rules and examples; Markdown is documentation.

Voice v2 additionally supports pinned corpus dependencies, exact example refs and
evidence refs. Corpus resources are separate from voice inheritance. Compiled
context/lock v2 retain resource identities and selected-material lineage; v1 formats
remain supported. See [corpus repositories](corpus-repository.md).

Composition is a local, explicit dependency graph. Bind parents with
`--bind PACK_ID=LOCAL_DIRECTORY`. Every edge pins ID, exact version and digest.
There are no network loaders, hooks, pack-defined code or model endpoints. The
canonical pack digest includes every field in `voice.json`. A compiled lock pins
the engine and ordered dependency identities; stale locks fail.

Common supplies soft defaults. An author, register-scoped rule or project overlay
may replace a soft rule using a new unique ID and `overrides: [old_id]`. Overrides
require identical scopes; constraints cannot be replaced. Duplicate IDs, missing
parents, cycles, explicit conflicts and contradictory literal constraints fail.
Permissions only narrow. Engine source/privacy boundaries cannot be overridden.

Rules filter by language, register and explicit tags. Channel and named character
scopes remain attached to exported instructions. Optional `modes` restricts the
supported language/register combinations and marks unvalidated adaptations.
Character constraints apply only inside the named dialogue; deterministic checking
requires caller-supplied Unicode spans when character attribution is unavailable.

Only reviewed examples with retrieval rights and the actual model-host permission
can be selected. Negative examples are visibly marked; examples can require an
explicit tag. Selection cycles across work IDs, with stable ID/priority ordering,
then includes whole elements within the codepoint budget. Mandatory context that
cannot fit causes `BUDGET_EXCEEDED`; omitted optional rules/examples are reported.

`qg-json-v1`: sorted JSON keys, compact separators, UTF-8 without ASCII escaping,
finite numbers, and one trailing LF. No time or duration enters a context digest.
`build_id` hashes the canonical context with that field removed. Check validates
this digest. Integrity does not establish permission provenance or literary quality.

Check offsets are zero-based, half-open Python Unicode codepoint ranges in the
unaltered draft. Literal checks conservatively exclude Markdown code, blockquotes,
paired quotations and dash-led dialogue from narration. This is a bounded parser,
not full CommonMark or a linguistic narrator detector. Supply character spans for
known dialogue. Human-review rules yield a checklist, never an author similarity score.
