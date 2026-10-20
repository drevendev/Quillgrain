"""Generate the shipped, closed Draft 2020-12 contracts. No private input."""
import json
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "src/quillgrain/schemas"
S = {"type": "string"}
H = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
I = {"type": "integer", "minimum": 0}
B = {"type": "boolean"}


def enum(*values):
    return {"enum": list(values)}


def arr(item=S):
    return {"type": "array", "items": item}


def obj(props, required=None):
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": list(props) if required is None else required}


VIS = enum("public", "private", "local_only")
STATUS = enum("CANDIDATE", "REVIEWED", "VALIDATED", "RETIRED")
PERMS = obj(dict(local_analysis=B, retrieval=B, private_git_excerpt=B,
                 approved_model_hosts=arr(), public_redistribution=B))
SCOPE = obj(dict(languages=arr(), registers=arr(), tags=arr(),
                 channel=enum("all", "narration", "dialogue"), characters=arr()), [])
RULE = obj(dict(id=S, kind=enum("preference", "constraint"), scope=SCOPE,
                instruction=S, priority=I, enforcement=enum("human_review", "required_literal", "forbidden_literal", "max_chars"),
                evidence_ids=arr(), origin=enum("designed_default", "observed", "owner_preference", "editorial_hypothesis"),
                status=STATUS, overrides=arr(), conflicts_with=arr(), required=B,
                severity=enum("warning", "error"),
                parameters=obj(dict(literal=S, max_chars=I), [])),
           ["id", "kind", "scope", "instruction", "priority", "enforcement", "evidence_ids", "origin", "status"])
EXAMPLE = obj(dict(id=S, text=S, before=S, language=S, register=S, source_id=S,
                   work_id=S, channel=enum("narration", "dialogue"), character_id=S,
                   permissions=PERMS, visibility=VIS, role=enum("positive", "negative", "before_after"),
                   tags=arr(), priority=I, authorship=S, status=STATUS),
              ["id", "text", "language", "register", "source_id", "work_id", "channel", "permissions", "visibility", "role", "tags", "priority", "authorship", "status"])
PARENT = obj(dict(id=S, version=S, digest=H))
PACK = obj(dict(schema_version={"const": "quillgrain.voice-pack/v1"}, id=S,
                version={"type": "string", "pattern": r"^\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]+)?$"},
                visibility=VIS, status=STATUS, languages=arr(), registers=arr(),
                extends=arr(PARENT), rules=arr(RULE), examples=arr(EXAMPLE),
                provenance=arr(obj(dict(id=S, kind=S, note=S))),
                compatibility=obj(dict(engine={"const": "0.1"}, schema={"const": "v1"})),
                permissions=PERMS, human_review=obj(dict(reviewer=S, reference=S, languages=arr(), registers=arr())),
                limitations=arr(), modes=arr(obj(dict(language=S, register=S, status=enum("CANDIDATE", "REVIEWED", "UNVALIDATED_ADAPTATION"))))),
           ["schema_version", "id", "version", "visibility", "status", "languages", "registers", "extends", "rules", "examples", "provenance", "compatibility", "permissions"])
CORPUS = obj(dict(schema_version={"const": "quillgrain.corpus-item/v1"}, id=S, work_id=S,
                  source_kind=S, source_alias=S, relative_locator=S, raw_sha256=H,
                  extraction_profile=S, extracted_sha256=H, language=S, register=S,
                  authorship=enum("owner_declared_human", "human_edited", "ai_assisted", "quoted", "unknown"),
                  selection=enum("candidate", "reference", "holdout", "excluded"), rights=S,
                  permissions=PERMS, approval=obj(dict(by=S, basis=S)), visibility=VIS,
                  ranges=arr(obj(dict(start_line=I, end_line=I))), limitations=arr(), duplicate_of=S),
             ["schema_version", "id", "work_id", "source_kind", "source_alias", "relative_locator", "raw_sha256", "extraction_profile", "extracted_sha256", "language", "register", "authorship", "selection", "rights", "permissions", "approval", "visibility", "ranges", "limitations"])
CONTEXT = obj(dict(schema_version={"const": "quillgrain.compiled-context/v1"}, build_id=H,
                   engine_version=S, canonicalization={"const": "qg-json-v1"},
                   packs=arr(PARENT), language=S, register=S, target=S, model_host=S, tags=arr(),
                   rules_applied=arr(RULE), rules_omitted=arr(obj(dict(id=S, reason=S))), rules_overridden=arr(obj(dict(id=S, by=S))),
                   examples_selected=arr(EXAMPLE), examples_omitted=arr(obj(dict(id=S, reason=S))),
                   budget=obj(dict(unit={"const": "unicode_codepoints"}, max_codepoints=I, used_codepoints=I)),
                   visibility=VIS, permissions=PERMS, prompt_payload=S, warnings=arr(),
                   lock_digest=H, conflict_report=arr()))
FINDING = obj(dict(rule_id=S, severity=enum("warning", "error"), method=S,
                   start=I, end=I, explanation=S, review=S))
CHECK = obj(dict(schema_version={"const": "quillgrain.check-report/v1"}, draft_sha256=H,
                 context_hash=H, engine_version=S, findings=arr(FINDING), skipped_checks=arr(), errors=arr()))
FEEDBACK = obj(dict(schema_version={"const": "quillgrain.feedback/v1"}, before_sha256=H,
                    after_sha256=H, context_id=H, run_id=S, before=S, after=S, note=S,
                    reason=enum("voice", "fact", "structure", "taste", "project_constraint", "one_off", "unknown"),
                    scope=SCOPE, proposed_rule_ids=arr(), decision_status={"const": "CANDIDATE"}, visibility=VIS))
RUN = obj(dict(schema_version={"const": "quillgrain.evaluation-run/v1"}, id=S, case_id=S,
               group_id=S, split=S, arm=enum("B0", "B1", "B2"), engine_version=S,
               pack_revisions=arr(PARENT), model_surface={"type": ["string", "null"]},
               model_id={"type": ["string", "null"]}, generation_options={"type": "object"},
               input_hash=H, prompt_hash=H, raw_output={"type": ["string", "null"]},
               raw_output_hash={"anyOf": [H, {"type": "null"}]},
               edited_output={"type": ["string", "null"]}, warnings=arr(), evaluator={"type": ["string", "null"]},
               human_decision={"type": ["string", "null"]},
               status=enum("NOT_RUN", "LIVE", "MOCK", "FAILED"),
               quality_status={"const": "HUMAN_REVIEW_PENDING"},
               session_id={"type": ["string", "null"]}, independence={"type": ["string", "null"]}))

if __name__ == "__main__":
    DEST.mkdir(parents=True, exist_ok=True)
    for name, schema in {"voice-pack": PACK, "corpus-item": CORPUS, "compiled-context": CONTEXT,
                         "check-report": CHECK, "feedback": FEEDBACK, "evaluation-run": RUN}.items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (DEST / (name + ".json")).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
