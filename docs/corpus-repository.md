# Versioned private source repositories

Quillgrain 0.1.0rc4 adds local corpus resources without network loaders. The public
engine and public Common pack contain no private writing or private metadata.
An approved PRIVATE corpus repository is the explicit exception to the older rule
that every normalized source must stay outside Git. Unapproved sources, absolute
locators, raw runs, model outputs, metrics, keys and exports still stay outside Git.

## Identity and permissions

`quillgrain.corpus/v1` identifies a private catalog. Closed `corpus-source/v1` and
`corpus-fragment/v1` schemas describe stable source/work IDs, immutable revisions,
authorship, permissions, explicit storage approval and exact reviewed spans.
A revision's identity hashes its original/text hashes and extraction profile.
Moving or renaming a file does not change a stored source ID. Legacy path-derived
IDs should be preserved through an explicit migration map.

Full sources and bounded excerpts have distinct storage modes; metadata-only cards
have no stored revisions. Private storage approval does not grant model inference,
private excerpt reuse or public redistribution. Source and example-use permissions
intersect. Protected work groups and known duplicate hashes cannot become examples.
Mixed/assisted authorship stays declared; unknown/quoted fragments cannot be selected.

Original snapshots and text views are separate immutable objects. The generic
ingest API preserves a supplied view; it does not claim to automatically attribute
authors or implement dialogue extraction. Existing narration extraction is one
specific profile. Other profiles require explicit prepared views and review.

## Voice v2 and reproducibility

Voice v1 remains supported unchanged. Voice v2 adds `corpus_dependencies`,
`example_refs` and `evidence_refs`. A dependency pins ID/version/catalog digest;
the digest includes the manifest and every registered source/fragment record.
An unrelated catalog change therefore requires an explicit dependency refresh in
this initial implementation. Corpus resources are not voice inheritance parents.

Example refs pin source/work/revision/fragment identities and the exact text hash,
with scope, tags and permissions for this particular use. An evidence ref supports
a rule without inserting prose into the model payload. A null evidence revision
means metadata-only historical provenance, not reproducible textual evidence.

```text
qg pack build --pack PRIVATE_VOICE --bind BASE_ID=LOCAL_BASE --corpus-bind CORPUS_ID=LOCAL_CORPUS --language ru --register essay --tag examples.owner.local --example-pool examples.owner.local --host ollama --out PRIVATE_OUTPUT
qg pack build --pack PRIVATE_VOICE --bind BASE_ID=LOCAL_BASE --examples none --language ru --register essay --host ollama --out PRIVATE_RULES_OUTPUT
```

Bindings are trusted caller-supplied local paths. There is no GitHub credential,
submodule update, endpoint execution or implicit network request. A missing or stale
corpus fails when matching refs are requested. Off-scope refs are reported without
reading content. Explicit `--examples none` omits both inline and referenced examples;
it needs no corpus checkout and reports that corpus contents were not loaded.

Compiled context v2 and lock v2 retain corpus identities and selected-material
lineage. Context digests exclude local paths and timestamps. The selected examples
are embedded in the export; a consumer does not need repository access. Consumers
must explicitly support v2; a migration does not install or mutate consumer runtimes.
Legacy v1 contexts remain valid. Public builds reject private corpus references.

## Inspection and local maintenance

`qg corpus init`, `add`, `fragment`, `validate`, `search`, `impact` and `qg explain`
operate locally. Search filters metadata by tags/language/register and never ranks
by private text size. Existing compilation retains deterministic priority and
work-level diversity with whole-example budget omission. There is no vector index.

`explain` writes rule origins/evidence IDs, chosen source lineages and omissions.
`impact` inspects only explicitly supplied packs and contexts. It cannot discover
unknown exported copies or revoke pasted text. Rights changes require synchronizing
the trusted local catalog and refreshing dependencies; an old offline snapshot
cannot know a later remote revocation. Hashes establish integrity, not permission
provenance, source completeness, absence from model pretraining or writing quality.

Private corpus checks run locally. No GitHub Actions or external CI may receive
private corpus data. Public engine tests use only original synthetic fixtures.
Tags are not access controls; separate collaborators may require separate repos.
