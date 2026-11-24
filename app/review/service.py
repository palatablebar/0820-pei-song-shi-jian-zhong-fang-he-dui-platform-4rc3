from datetime import datetime, timedelta, timezone
from hashlib import sha256
from time import monotonic

from app.business import DomainIssue
from app.config import OWNER_GUARD_SECONDS, RULE_VERSION
from app.modules.pipeline import run


def moment():
    return datetime.now(timezone.utc)


def now():
    return moment().isoformat(timespec="milliseconds")


def actor_of(value):
    if not isinstance(value, str) or not (1 <= len(value.strip()) <= 40):
        raise DomainIssue("ACTOR_REQUIRED")
    return value.strip()


def point(at=None):
    if at is None:
        return moment()
    if isinstance(at, datetime):
        aware = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc)
    return datetime.fromisoformat(at)


def execute(store, data, actor):
    start = monotonic()
    fingerprint = sha256(data).hexdigest()
    run_id = sha256(f"{RULE_VERSION}:{fingerprint}".encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != "RUN_NOT_FOUND":
            raise
    report = run(data)
    owner = actor_of(actor)
    report["manifest"] = dict(
        sha256=fingerprint,
        version=RULE_VERSION,
        created=now(),
        duration_ms=round((monotonic() - start) * 1000, 3),
        bytes=len(data),
        run_id=run_id,
    )
    return store.register(run_id, report, owner)


def claim(store, run_id, actor, *, guard=None, at=None):
    owner = actor_of(actor)
    guard = OWNER_GUARD_SECONDS if guard is None else guard
    instant = point(at)
    current = store.load(run_id)
    if current["owner"] == owner:
        return current
    stamp = instant.isoformat(timespec="milliseconds")
    threshold = (instant - timedelta(seconds=guard)).isoformat(timespec="milliseconds")
    return store.claim(run_id, owner, stamp, threshold)


def release(store, run_id, actor, *, at=None):
    owner = actor_of(actor)
    stamp = point(at).isoformat(timespec="milliseconds")
    return store.release(run_id, owner, stamp)


def review(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue("REVIEW_FIELDS")
    revision, status, note = (values.get(key) for key in ("revision", "status", "note"))
    if (
        type(revision) is not int
        or revision < 0
        or status not in ("APPROVED", "HELD")
        or not isinstance(note, str)
        or not (3 <= len(note.strip()) <= 200)
    ):
        raise DomainIssue("REVIEW_FIELDS")
    owner = actor_of(values.get("actor"))
    current = store.load(run_id)
    if current["owner"] != owner:
        raise DomainIssue("OWNER_MISMATCH")
    if revision != current["revision"]:
        raise DomainIssue("STALE_REVIEW")
    if current["status"] == "APPROVED":
        raise DomainIssue("RUN_FINALIZED")
    if status == "APPROVED" and not current["report"]["balance"]["releasable"]:
        raise DomainIssue("UNRESOLVED_ISSUES")
    return store.revise(run_id, revision, status, note.strip(), owner, now())
