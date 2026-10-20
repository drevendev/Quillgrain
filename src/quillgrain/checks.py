"""Literal/length checks with Python Unicode offsets. Never a quality score."""
import re
from . import __version__
from .contracts import validate, verify_context
from .io import sha, QGError


def regions(text):
    """Conservative Markdown/plain-text regions, keeping original offsets."""
    labels = ["narration"] * len(text)
    fence, offset = None, 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if fence or marker:
            labels[offset:offset + len(line)] = ["code"] * len(line)
            if marker:
                if fence and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                    fence = None
                elif not fence:
                    fence = marker[1]
        elif stripped.startswith(">"):
            labels[offset:offset + len(line)] = ["quote"] * len(line)
        elif re.match(r"[—–]\s", stripped):
            labels[offset:offset + len(line)] = ["dialogue"] * len(line)
        offset += len(line)
    for pattern, label in [(r"`[^`\n]+`", "code"), (r'"[^"\n]*"|«[^»]*»|“[^”]*”', "quote")]:
        for match in re.finditer(pattern, text):
            for pos in range(match.start(), match.end()):
                if labels[pos] == "narration":
                    labels[pos] = label
    return labels


def check(text, context, scopes=()):
    verify_context(context)
    labels = regions(text)
    characters = [None] * len(text)
    occupied = set()
    for scope in scopes:
        start, end = scope["start"], scope["end"]
        if not (0 <= start <= end <= len(text)) or occupied.intersection(range(start, end)):
            raise QGError("INVALID_CHARACTER_SPAN")
        occupied.update(range(start, end))
        for pos in range(start, end):
            if labels[pos] != "code":
                labels[pos] = "dialogue"
                characters[pos] = scope["character"]
    findings, skipped = [], []
    for rule in context["rules_applied"]:
        method, scope = rule["enforcement"], rule["scope"]
        if method == "human_review":
            skipped.append(rule["id"] + ":HUMAN_REVIEW_REQUIRED")
            continue
        channel = scope.get("channel", "all")
        allowed = [lab not in ("code", "quote") and (channel == "all" or lab == channel)
                   and (not scope.get("characters") or characters[i] in scope["characters"])
                   for i, lab in enumerate(labels)]
        if scope.get("characters") and not any(allowed):
            skipped.append(rule["id"] + ":CHARACTER_SCOPE_UNAVAILABLE")
            continue
        params = rule["parameters"]
        spans = []
        if method in ("required_literal", "forbidden_literal"):
            literal = params["literal"]
            matches = [(m.start(), m.end()) for m in re.finditer(re.escape(literal), text)
                       if all(allowed[m.start():m.end()])]
            if method == "required_literal" and not matches:
                spans = [(0, 0)]
            elif method == "forbidden_literal":
                spans = matches
        elif method == "max_chars":
            if sum(allowed) > params["max_chars"]:
                spans = [(0, len(text))]
        for start, end in spans:
            findings.append(dict(rule_id=rule["id"], severity=rule.get("severity", "warning"), method=method,
                                 start=start, end=end, explanation=rule["instruction"],
                                 review="Review against the separate brief; this check does not establish truth or quality."))
    report = dict(schema_version="quillgrain.check-report/v1", draft_sha256=sha(text.encode("utf-8")),
                  context_hash=context["build_id"], engine_version=__version__, findings=findings,
                  skipped_checks=skipped, errors=[])
    return validate(report, "check-report")
