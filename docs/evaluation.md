# Technical checks, model evidence, human review

`qg eval prepare --cases cases --out runs` creates B0/B1/B2 packets. Each local case
JSON supplies `id`, `brief`, `baseline`, `contexts: {B1, B2}` paths and optionally
`model_surface`, `model_id`, `generation_options`, `split`, and `group_id`.
Brief/baseline hashes match across arms. A separate new session or stateless model
request must receive only its own packet, never competing responses.

There is no model runner. Use an already authorized writing tool, keep its untouched
response and the available model/session identity, then record it:

```text
qg eval record --manifest runs/case/B0/run.json --output answer.md --surface SURFACE --model MODEL --session SESSION --independence DESCRIPTION
qg eval report --runs runs --out report
```

Runs begin NOT_RUN. LIVE requires explicit identity and an independence declaration;
MOCK and FAILED remain separate. A declaration records evidence supplied by the caller,
not proof that the engine observed a model. Unknown seed/cost/model revision stays
unknown. Raw runs are immutable through record; keep subsequent edits separately.
Report rejects unequal input hashes or visible model/options inside a comparison.

The report creates randomized anonymous live samples and a separate private mapping
key. Do not give the key to the reviewer. Filename blinding cannot hide every stylistic
cue. Owner feedback decides resemblance, usefulness, factual/canon fidelity and editing
effort. Technical success and LIVE output do not validate voice or imply adoption.

Use fresh development cases, then reserve genuinely untouched works/topics for later
holdouts. In addition to no-pack/Common/author comparisons, a future test should include
a short ordinary guide as a strong inexpensive baseline. Preserve failed attempts and
avoid tuning repeatedly on a supposed holdout.
