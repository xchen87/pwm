"""User journeys for the functional test. One function per journey, run in name order.

Each takes (api, check, run). Add a journey whenever a slice adds user-visible behaviour.
"""

from typing import Any


def _q3(api: Any) -> dict[str, Any]:
    items = api.get("/commitments")
    return next(i for i in items if "Q3" in i["evidence_quote"] and i["direction"] == "by_user")


def journey_10_commitment_radar(api: Any, check: Any, run: Any) -> None:
    items = api.get("/commitments")
    check(len(items) >= 10, "needs-attention lists the possible commitments")
    check(
        all(i["review"] == "unreviewed" for i in items if i["origin"] != "user_stated"),
        "nothing extracted from mail arrives already confirmed",
    )
    check(all(i["evidence_quote"] for i in items), "every item carries its evidence quote")

    item = _q3(api)
    detail = api.get(f"/assertions/{item['id']}")
    check(
        detail["context_quote"] and detail["context_before"] + detail["context_after"],
        "source inspection shows the quote in its surrounding text",
    )

    api.post(f"/assertions/{item['id']}/status", {"status": "done"}, expect=409)
    confirmed = api.post(f"/assertions/{item['id']}/confirm")
    check(confirmed["review"] == "confirmed", "confirm marks the commitment confirmed")


def journey_11_decisions_survive_reprocessing(api: Any, check: Any, run: Any) -> None:
    item = _q3(api)
    run("uv", "run", "python", "-m", "pwm.cli", "reprocess")
    check(_q3(api)["review"] == "confirmed", "a confirmation survives reprocessing")
    check(_q3(api)["id"] == item["id"], "reprocessing does not duplicate assertions")


def journey_12_edit_dismiss_done(api: Any, check: Any, run: Any) -> None:
    items = api.get("/commitments")
    target = next(i for i in items if i["review"] == "unreviewed" and i["direction"] == "to_user")
    fixed = api.post(
        f"/assertions/{target['id']}/correct", {"what": "Edited by the test", "due": "2026-10-01"}
    )
    check(
        fixed["origin"] == "user_stated" and fixed["review"] == "confirmed",
        "an edit is the user's statement",
    )
    check(
        fixed["related"][0]["relation"] == "supersedes",
        "the edit supersedes the original, which is kept",
    )

    other = next(i for i in api.get("/commitments") if i["review"] == "unreviewed")
    api.post(f"/assertions/{other['id']}/dismiss")
    ids = [i["id"] for i in api.get("/commitments")]
    check(
        other["id"] not in ids and target["id"] not in ids,
        "dismissed and replaced items leave the list",
    )

    done = api.post(f"/assertions/{fixed['id']}/status", {"status": "done"})
    check(done["status"] == "done", "a confirmed commitment can be marked done")
    api.get("/assertions/00000000-0000-0000-0000-000000000000", expect=404)


def journey_20_home_and_brief(api: Any, check: Any, run: Any) -> None:
    api.post("/visits")
    home = api.get("/home")
    check(len(home["what_changed"]) >= 2, "home shows what changed")
    check(
        any(
            w["item"]["kind"] == "changed" and w["item"]["previous_value"]
            for w in home["what_changed"]
        ),
        "a change shows the old value next to the new one",
    )
    check(
        len(home["needs_attention"]) <= 3 < home["needs_attention_total"],
        "home previews needs-attention",
    )
    check(
        any("sister" in r["evidence_quote"] for r in home["remembered"]),
        "home shows what the user asked to remember",
    )

    brief = api.post("/briefs?period=weekly")
    check(len(brief["items"]) >= 3, "a weekly brief is generated")
    check(
        all(
            w["headline"].startswith(("Possible", "It looks like", "Two sources"))
            for w in brief["items"]
            if not w["item"]["is_fact"]
        ),
        "unconfirmed brief items are worded as possibilities",
    )
    check(
        len({w["item"]["assertion_id"] for w in brief["items"]}) == len(brief["items"]),
        "no item repeats in a brief",
    )
    notes = api.get("/notifications")
    check(
        notes and notes[0]["title"] == "Your World Brief is ready",
        "the brief notification is generic",
    )
    check(notes[0]["deep_link"].endswith(brief["id"]), "the notification links to the brief")
    api.post("/events", {"name": "brief_opened", "subject_id": brief["id"]})
    api.post("/events", {"name": "not_an_event"}, expect=422)
    api.post("/notifications/read")
    check(api.get("/home")["unread_notifications"] == 0, "notifications can be marked read")
