from .contracts import validate, verify_context
from .io import sha, QGError


def record(before, after, context, note, reason="unknown", run_id="unknown", scope=None, proposed=()):
    verify_context(context)
    if reason in ("fact", "one_off") and proposed:
        raise QGError("FACT_OR_ONE_OFF_IS_NOT_VOICE_RULE", 3)
    return validate(dict(schema_version="quillgrain.feedback/v1", before_sha256=sha(before.encode("utf-8")),
                         after_sha256=sha(after.encode("utf-8")), context_id=context["build_id"], run_id=run_id,
                         before=before, after=after, note=note, reason=reason, scope=scope or {},
                         proposed_rule_ids=list(proposed), decision_status="CANDIDATE", visibility="private"), "feedback")
