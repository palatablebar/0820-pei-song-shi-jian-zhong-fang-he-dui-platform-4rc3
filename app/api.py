from flask import Blueprint, Response, current_app, jsonify, request

from app.business import DomainIssue
from app.config import OWNER_GUARD_SECONDS
from app.evidence.render import artifact
from app.inputs import read_input
from app.modules.pipeline import run
from app.review.service import claim, execute, release, review

api = Blueprint("api", __name__, url_prefix="/api")
STAGES = {"intake": 1, "prepare": 2, "calculate": 3, "policy": 4, "balance": 5}


def presented(batch):
    batch["guard_seconds"] = OWNER_GUARD_SECONDS
    return jsonify(batch)


@api.post("/stages/<stage>")
def preview(stage):
    if stage not in STAGES:
        raise DomainIssue("STAGE_UNKNOWN")
    return jsonify(run(read_input(), STAGES[stage]))


@api.route("/runs", methods=["GET", "POST"])
def runs():
    store = current_app.extensions["runs"]
    if request.method == "GET":
        return jsonify(items=store.list())
    return presented(execute(store, read_input(), request.form.get("actor", "")))


@api.route("/runs/<run_id>", methods=["GET", "PATCH"])
def batch(run_id):
    store = current_app.extensions["runs"]
    if request.method == "GET":
        return presented(store.load(run_id))
    return presented(review(store, run_id, request.get_json(silent=True)))


@api.post("/runs/<run_id>/claim")
def take_over(run_id):
    values = request.get_json(silent=True) or {}
    return presented(claim(current_app.extensions["runs"], run_id, values.get("actor")))


@api.post("/runs/<run_id>/release")
def hand_back(run_id):
    values = request.get_json(silent=True) or {}
    return presented(
        release(current_app.extensions["runs"], run_id, values.get("actor"))
    )


@api.get("/runs/<run_id>/evidence")
def export(run_id):
    report = current_app.extensions["runs"].load(run_id)
    return Response(
        artifact(report),
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="review-{report["id"][:12]}.json"',
            "Cache-Control": "no-store",
        },
    )
