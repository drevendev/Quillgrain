# Private rules-only skill recipes

`python -m quillgrain.skill_profiles` builds portable multi-register Codex and
Claude skills from a pinned JSON recipe. It makes no model calls, does not read
corpus bodies, and does not install or replace a working skill. Keep actual
private recipes and outputs outside this public checkout.

```text
python -m quillgrain.skill_profiles --recipe PRIVATE_RECIPE --pack PRIVATE_PACK --bind PARENT_ID=PARENT_PATH --out NEW_PRIVATE_OUTPUT
```

A `quillgrain.skill-recipe/v1` record declares `profile`, `skill_name`, `description`,
`display_name`, `short_description`, `deployment_id`, `deployment_version`,
`visibility` (private), `language`, `default_register`, `registers` (an ordered
mapping to task labels), `max_chars`, `source_profiles` (exact chain references),
and `hosts` (codex and/or claude). Optional `instructions` are the small private
entrypoint differences; `assets` maps `references/*.md` destinations to relative
files next to the recipe. Tests contain a complete original synthetic recipe.

An already permitted host needs no grant. A denied host requires a
`rules_only_grant` with its exact `host`, source references for every denied
input, an authorization `id` and `basis`, plus a version `snapshot_suffix`.
It records separately obtained authority; its presence does not establish that
the operator is authorized. Such snapshots drop examples before composition.
The canonical inputs are unchanged. No grant may activate an example or infer
permission for another host. Every final deployment narrows its destination to
one host and selects no examples.

Outputs include each host's skill, normalized-timestamp ZIP, and a build receipt
with exact input and engine-file digests. Compare manifests and unpacked members;
ZIP byte identity is also reproducible in the same Python/zlib environment.
`--compare-installed PATH` reports a Codex candidate/installed difference without
writing to the installed location. Back up the installed skill before any
separately requested replacement; rollback restores that exact folder.

The stdlib-only `scripts/voice_context.py` verifies file/context/lock digests,
mode, host and rules-only scope, then prints the selected payload with `--show`.
It works with Python after relocation without the engine or source packs.
It checks integrity, not publisher authenticity, factual truth or literary quality.

The same `lengths.py` source is used by the engine and bundled skills. For an
explicit word budget it checks parts and the whole. Before a next part:

```text
python lengths.py --input PREFIX --plan-next --next-range 100:180 --remaining-range 80:150 --min-words 400 --max-words 550
```

Repeated `--input` files are the actual accepted prefix; repeated remaining ranges
describe only parts after the next one. Empty endpoints are unbounded. The result
is READY with a feasible next interval, or CONFLICT. An incomplete prefix is not
declared an under-length finished text. Omit `--input` for an empty prefix.
After generation use the normal total/part check. A counter detects a miss; it
does not guarantee a model will obey, authorize regeneration or certify style.

Routing, helper execution and prose quality need separate observed checks in the
actual assistant surface. Pure human-review rules do not become a programmatic
PASS when the structural checker skips them.
