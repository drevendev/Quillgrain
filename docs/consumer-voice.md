# External writing consumers

Export an explicitly selected voice for a local PatchPitch application:

```text
qg pack build --pack PATH_TO_PACK --register maker_announcement --language ru --target patchpitch --host ollama --tag delivery.vivid --tag social.telegram --max-chars 14000 --out NEW_OUTPUT
```

Supply dependency bindings as usual. Select local examples only when their rights
and tags allow it. The output includes `voice-bundle.json`: one JSON object with
`schema_version: quillgrain.voice-bundle/v1`, compiled `context` and matching `lock`.
It contains the actual selected rules/examples, not a locator to a private corpus.
The existing `patchpitch-legacy` field remains capped at 1,200 Unicode codepoints.

To replace generic examples with an explicitly selected local pool, pass both
`--tag examples.chosen` and `--example-pool examples.chosen`. Only examples
carrying that tag remain eligible; rules are unaffected. Merely adding a tag
does not remove untagged default examples. The selection report records omitted
defaults as `example_pool`. An empty pool stays empty, with no implicit fallback.

Consumers use the same engine verifier:

```python
from quillgrain.consumer import loads_bundle, verify_bundle

artifact = loads_bundle(file_text)
context = verify_bundle(artifact, model_host="ollama", language="ru",
                        register="maker_announcement", tags=["social.telegram"])
```

Version 1 limits the serialized artifact to 512,000 UTF-8 bytes and the compiled
budget to 24,000 Unicode codepoints. The consumer may impose a smaller model
budget. The compiler selects whole elements; required rules that cannot fit fail
compilation. `rules_omitted` and `examples_omitted` expose omissions. The verifier
checks schema, build and lock identity, exact rule/example assembly, scope and
retrieval/host permission. Errors use stable `QGError.code` values such as
`VOICE_LANGUAGE_MISMATCH`, `VOICE_CHANNEL_MISMATCH`, `LOCK_DIGEST_MISMATCH` and
`VOICE_BUDGET_UNSUPPORTED`. Integrity hashes are not proof of authorship or rights.

Apply style preferences in a separate bounded prompt section. Keep examples as
untrusted illustrative data and task facts separate. Preserve rule priority when
assembling soft preferences; facts, source exclusions and output constraints stay
authoritative. Import does not grant filesystem access, tools or publication.

Record the immutable build/pack identities and effective assembly hash with each
generation. User-selected replacement affects future requests only. A valid old
artifact is not corrupt: compare against an explicitly expected build to establish
freshness. Preserve original snapshots when restoring sessions or regenerating.

Private/local-only contexts remain local, including when embedded in saved
sessions. Do not put them in logs, telemetry, public examples or source archives.
Candidate warnings and language/register limitations remain visible. Successful
import is a technical property; author-voice quality needs human assessment with
the actual model. No network service or model provider is part of this interface.
