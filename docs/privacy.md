# Privacy and publication

Use separate repositories for the engine, public packs and private packs. Store
source locators, normalized text, inventories, metrics, raw runs, edits and exports
outside **every** Git worktree. A private repository does not license redistribution.

Source roots are explicit trusted local configuration. The engine never crawls the
computer, expands embeds, runs frontmatter or follows data-defined endpoints.
Visibility inherits the most restrictive input: public < private < local_only.
`--public` rejects a private pack; examples still require public redistribution.
Deleting a source does not recall older exports. Use context pack/example lineage
and rebuild dependent outputs after revocation. History cleanup is a separate task.

`approved_model_hosts` records actual destinations (`offline`, `chatgpt`, `codex`,
`ollama` are conventions, not authentication). Building an export does not send it.
Uploading a private context to a cloud model is a real transfer; inspect selected
examples and permissions first. Host labels cannot verify where a human later pastes
a file. Quillgrain has no telemetry and calls no model.

Public CI has only original synthetic fixtures and no private checkout, API key or
model server. Source distributions and wheels use an explicit file manifest. Run
`scripts/audit_public.py` on sources and archives with an optional private canary
file before publication. Inspect the actual member list as well: a secret scanner
alone cannot distinguish private prose from publishable fixtures. The allowlist is
an additional barrier, not an absolute data-loss prevention system.
