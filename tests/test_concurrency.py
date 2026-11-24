from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.business import DomainIssue
from app.review.service import claim, execute, review


def test_parallel_rerun_commits_single_row(store, clean):
    start = Barrier(4)

    def load():
        start.wait(3)
        return execute(store, clean, "值班员甲")

    with ThreadPoolExecutor(max_workers=4) as threads:
        results = list(threads.map(lambda _: load(), range(4)))
    assert all(result == results[0] for result in results)
    assert len(store.list()) == 1
    assert len(results[0]["handovers"]) == 1


def test_parallel_review_has_one_winner(store, dirty):
    run = execute(store, dirty, "值班员甲")
    start = Barrier(2)

    def attempt(note):
        start.wait(3)
        try:
            return review(
                store,
                run["id"],
                dict(revision=0, status="HELD", note=note, actor="值班员甲"),
            )["status"]
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(attempt, ["来源待检查", "分组待处理"]))
    assert sorted(results) == ["HELD", "STALE_REVIEW"]
    assert store.load(run["id"])["revision"] == 1


def test_parallel_claim_has_one_winner(store, clean):
    run = execute(store, clean, "值班员甲")
    with store.connect() as db:
        db.execute(
            "UPDATE runs SET owner_since=? WHERE id=?",
            ("2000-01-01T00:00:00.000+00:00", run["id"]),
        )
    start = Barrier(2)

    def attempt(actor):
        start.wait(3)
        try:
            return claim(store, run["id"], actor)["owner"]
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(attempt, ["值班员乙", "值班员丙"]))
    assert results.count("OWNER_ACTIVE") == 1
    winner = next(result for result in results if result != "OWNER_ACTIVE")
    loaded = store.load(run["id"])
    assert loaded["owner"] == winner
    assert [entry["action"] for entry in loaded["handovers"]] == ["CLAIM", "TAKEOVER"]
