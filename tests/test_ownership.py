from datetime import timedelta

import pytest

from app.business import DomainIssue
from app.review.service import claim, execute, release, review
from app.review.service import point as at_time

NIGHT = "夜班甲"
MORNING = "早班乙"


def since(run):
    return at_time(run["owner_since"])


def test_execute_registers_owner_and_first_handover(store, clean):
    run = execute(store, clean, NIGHT)
    assert run["owner"] == NIGHT and run["owner_since"]
    assert run["handovers"] == [
        dict(actor=NIGHT, action="CLAIM", at=run["handovers"][0]["at"])
    ]
    assert run["handovers"][0]["at"] == run["owner_since"]


def test_execute_requires_actor(store, clean):
    with pytest.raises(DomainIssue, match="ACTOR_REQUIRED"):
        execute(store, clean, "   ")


def test_review_requires_actor(store, clean):
    run = execute(store, clean, NIGHT)
    with pytest.raises(DomainIssue, match="ACTOR_REQUIRED"):
        review(store, run["id"], dict(revision=0, status="HELD", note="缺少值班员"))


def test_claim_rejected_within_guard(store, clean):  # TRAP-27
    run = execute(store, clean, NIGHT)
    with pytest.raises(DomainIssue, match="OWNER_ACTIVE"):
        claim(store, run["id"], MORNING, guard=60, at=since(run) + timedelta(seconds=59))
    assert store.load(run["id"])["owner"] == NIGHT


def test_claim_allowed_once_guard_expires(store, clean):  # TRAP-27
    run = execute(store, clean, NIGHT)
    taken = claim(
        store, run["id"], MORNING, guard=60, at=since(run) + timedelta(seconds=60)
    )
    assert taken["owner"] == MORNING
    assert [entry["action"] for entry in taken["handovers"]] == ["CLAIM", "TAKEOVER"]


def test_claim_allowed_after_release(store, clean):
    run = execute(store, clean, NIGHT)
    returned = release(store, run["id"], NIGHT)
    assert returned["owner"] == ""
    taken = claim(store, run["id"], MORNING)
    assert taken["owner"] == MORNING
    assert [entry["action"] for entry in taken["handovers"]] == [
        "CLAIM",
        "RELEASE",
        "TAKEOVER",
    ]


def test_release_by_stranger_is_rejected(store, clean):
    run = execute(store, clean, NIGHT)
    with pytest.raises(DomainIssue, match="OWNER_MISMATCH"):
        release(store, run["id"], MORNING)
    assert store.load(run["id"])["owner"] == NIGHT


def test_same_owner_claim_is_noop(store, clean):
    run = execute(store, clean, NIGHT)
    again = claim(store, run["id"], NIGHT)
    assert again["revision"] == run["revision"]
    assert len(again["handovers"]) == 1


def test_claim_unknown_run(store):
    with pytest.raises(DomainIssue, match="RUN_NOT_FOUND"):
        claim(store, "missing", MORNING)


def test_former_owner_submission_fails_after_takeover(store, clean):  # TRAP-28
    run = execute(store, clean, NIGHT)
    claim(store, run["id"], MORNING, guard=0)
    with pytest.raises(DomainIssue, match="OWNER_MISMATCH"):
        review(
            store,
            run["id"],
            dict(revision=0, status="APPROVED", note="夜班补交结论", actor=NIGHT),
        )
    assert store.load(run["id"])["status"] == "PENDING"


def test_new_owner_reviews_after_takeover(store, clean):
    run = execute(store, clean, NIGHT)
    claim(store, run["id"], MORNING, guard=0)
    output = review(
        store,
        run["id"],
        dict(revision=0, status="APPROVED", note="早班复核完成", actor=MORNING),
    )
    assert output["status"] == "APPROVED" and output["revision"] == 1


def test_new_owner_must_resolve_groups_before_approval(store, dirty):
    run = execute(store, dirty, NIGHT)
    claim(store, run["id"], MORNING, guard=0)
    with pytest.raises(DomainIssue, match="UNRESOLVED_ISSUES"):
        review(
            store,
            run["id"],
            dict(revision=0, status="APPROVED", note="差异尚未处理", actor=MORNING),
        )


def test_handover_trail_keeps_every_actor_and_time(store, clean):
    run = execute(store, clean, NIGHT)
    moment = since(run) + timedelta(hours=8)
    release(store, run["id"], NIGHT, at=moment)
    loaded = claim(store, run["id"], MORNING, at=moment + timedelta(minutes=5))
    trail = loaded["handovers"]
    assert [entry["actor"] for entry in trail] == [NIGHT, NIGHT, MORNING]
    assert [entry["action"] for entry in trail] == ["CLAIM", "RELEASE", "TAKEOVER"]
    assert [entry["at"] for entry in trail] == sorted(entry["at"] for entry in trail)


def test_http_handover_flow(client):
    run = client.post("/api/runs", data={"sample": "clean", "actor": NIGHT}).json
    assert run["owner"] == NIGHT and run["guard_seconds"] > 0
    blocked = client.post(f"/api/runs/{run['id']}/claim", json={"actor": MORNING})
    assert blocked.status_code == 409 and blocked.json["code"] == "OWNER_ACTIVE"
    returned = client.post(f"/api/runs/{run['id']}/release", json={"actor": NIGHT})
    assert returned.status_code == 200 and returned.json["owner"] == ""
    taken = client.post(f"/api/runs/{run['id']}/claim", json={"actor": MORNING})
    assert taken.status_code == 200 and taken.json["owner"] == MORNING
    stale = client.patch(
        f"/api/runs/{run['id']}",
        json=dict(revision=0, status="HELD", note="夜班补交结论", actor=NIGHT),
    )
    assert stale.status_code == 409 and stale.json["code"] == "OWNER_MISMATCH"
    done = client.patch(
        f"/api/runs/{run['id']}",
        json=dict(revision=0, status="APPROVED", note="早班复核完成", actor=MORNING),
    )
    assert done.status_code == 200 and done.json["status"] == "APPROVED"
    trail = client.get(f"/api/runs/{run['id']}").json["handovers"]
    assert [entry["action"] for entry in trail] == ["CLAIM", "RELEASE", "TAKEOVER"]
    assert all(entry["actor"] and entry["at"] for entry in trail)


def test_http_execute_requires_actor(client):
    response = client.post("/api/runs", data={"sample": "clean"})
    assert response.status_code == 422 and response.json["code"] == "ACTOR_REQUIRED"
