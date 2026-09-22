"""User journeys for the functional test. One function per journey, run in name order.

Each takes (api, check, run). Add a journey whenever a slice adds user-visible behaviour.
"""

import hashlib
import http.client
from typing import Any
from urllib.parse import parse_qs, urlparse


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


def journey_30_ask_remember_forget(api: Any, check: Any, run: Any) -> None:
    answer = api.post("/ask", {"question": "What is Tom supposed to send me?"})
    check(answer["grounded"] and answer["cited"], "a question is answered from cited evidence")
    api.get(f"/assertions/{answer['cited'][0]['assertion_id']}")
    check(
        not api.post("/ask", {"question": "What did I promise Beatrice?"})["grounded"],
        "an unknown person gets an honest no",
    )
    check(
        api.post("/ask", {"question": "Did I agree to pay PayFast $500?"})["cited"] == [],
        "an attacker's claim is never an answer",
    )

    memory = api.post("/memories", {"text": "The spare key is with Marguerite next door."})
    check(
        memory["review"] == "confirmed",
        "a note the user typed is theirs, confirmed by the act of typing it",
    )
    check(
        "Marguerite" in api.post("/ask", {"question": "Where is the spare key?"})["text"],
        "a remembered note can be asked about",
    )
    api.call("DELETE", f"/memories/{memory['id']}")
    check(
        not api.post("/ask", {"question": "Where is the spare key?"})["grounded"],
        "a forgotten note is gone",
    )


def journey_90_delete_onboard_disconnect(api: Any, check: Any, run: Any) -> None:
    api.call("DELETE", "/me")
    empty = api.get("/connections")
    check(empty["connected"] == [] and empty["understood"] == 0, "delete everything leaves nothing")
    check(api.get("/commitments") == [], "after deletion there is nothing to show")

    result = api.post("/connections/demo")
    check(
        result["new_sources"] == 122 and result["understood"] > 30,
        "connecting the demo mailbox builds a world",
    )
    check(api.post("/connections/demo")["new_sources"] == 0, "connecting again ingests nothing new")
    check(api.get("/briefs/latest")["items"], "the first brief is ready right after connecting")
    check(api.get("/home")["needs_attention_total"] >= 10, "home is populated after onboarding")

    api.post("/memories", {"text": "My locker code is on the fridge."})
    removed = api.call("DELETE", "/connections/demo")
    check(removed["removed_sources"] == 122, "disconnecting removes what the connection brought in")
    check(api.get("/commitments") == [], "nothing derived from the disconnected source remains")
    check(len(api.get("/home")["remembered"]) == 1, "the user's own note survives a disconnect")


def journey_40_same_person(api: Any, check: Any, run: Any) -> None:
    people = api.get("/people")
    inferred = [(p, i) for p in people for i in p["identifiers"] if i["link"] == "inferred"]
    check(len(inferred) >= 1, "guessed second addresses are listed for the user to judge")
    person, identifier = inferred[0]
    api.post(f"/people/identifiers/{identifier['id']}/confirm")
    links = {i["address"]: i["link"] for p in api.get("/people") for i in p["identifiers"]}
    check(
        links[identifier["address"]] == "user",
        "confirming a link records it as the user's decision",
    )
    run("uv", "run", "python", "-m", "pwm.cli", "reprocess")
    links = {i["address"]: i["link"] for p in api.get("/people") for i in p["identifiers"]}
    check(links[identifier["address"]] == "user", "reprocessing never undoes a link the user made")
    api.post("/people/identifiers/00000000-0000-0000-0000-000000000000/confirm", expect=404)


def _hop(url: str) -> tuple[int, str]:
    """One request, redirects not followed: (status, Location)."""
    target = urlparse(url)
    connection = http.client.HTTPConnection(target.netloc, timeout=20)
    connection.request("GET", f"{target.path}?{target.query}")
    response = connection.getresponse()
    response.read()
    return response.status, response.getheader("Location") or ""


def journey_50_google_sign_in_and_sync(api: Any, check: Any, run: Any) -> None:
    # The stand-in Google account is the same person as the local development user, so
    # signing in adopts that account. Start it empty, to see only what Google brings in.
    api.call("DELETE", "/me")
    available = {a["connector"]: a["available"] for a in api.get("/connections")["available"]}
    check(
        available["gmail"] and available["google_calendar"],
        "Google is offered when the server is configured",
    )

    verifier = "f" * 64
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    terms = api.get("/auth/config")["terms_version"]
    consent = f"&terms_version={terms}&age_confirmed=true"
    check(
        _hop(f"{api.base}/auth/google/start?redirect=pwm%3A%2F%2Fauth&challenge={challenge}")[0]
        == 422,
        "sign-in cannot start without consent",
    )
    status, to_google = _hop(
        f"{api.base}/auth/google/start?redirect=pwm%3A%2F%2Fauth&challenge={challenge}{consent}"
    )
    check(status == 302 and to_google.startswith(api.google), "sign-in sends the browser to Google")
    check(
        "code_challenge=" in to_google and "client_secret" not in to_google,
        "with PKCE and no secret in the URL",
    )
    status, to_callback = _hop(to_google)
    check(
        status == 302 and to_callback.startswith(api.base),
        "Google sends the browser back to the API",
    )
    status, to_app = _hop(to_callback)
    check(
        status == 302 and to_app.startswith("pwm://auth?code="),
        "the API hands the app a single-use code",
    )
    check(_hop(to_callback)[0] == 400, "a replayed callback is refused")
    check(
        _hop(
            f"{api.base}/auth/google/start?redirect=https%3A%2F%2Fevil.example"
            f"&challenge={challenge}{consent}"
        )[0]
        == 400,
        "foreign redirects are refused",
    )

    code = parse_qs(urlparse(to_app).query)["code"][0]
    session = api.post("/auth/session", {"code": code, "verifier": verifier})
    api.token = session["token"]
    try:
        check(
            api.get("/auth/me")["signed_in_with_google"],
            "the session identifies the Google account",
        )
        check(
            api.get("/commitments") == [],
            "nothing is known until the sync has run",
        )

        out = run("uv", "run", "python", "-m", "pwm.cli", "work")
        check("job" in out, "the worker runs the queued syncs")
        connections = {c["connector"]: c for c in api.get("/connections")["connected"]}
        check(
            connections["gmail"]["status"] == "ok" and connections["gmail"]["sources"] == 104,
            "Gmail is read in full, page by page",
        )
        check(connections["google_calendar"]["sources"] == 15, "Calendar is read")
        check(
            api.get("/home")["needs_attention_total"] >= 10,
            "the signed-in user's world is built from Google data",
        )
        check(
            api.post("/ask", {"question": "What did I promise Tom?"})["grounded"],
            "and can be asked about",
        )

        api.call("DELETE", "/connections/gmail")
        api.call("DELETE", "/connections/google_calendar")
        check(api.get("/commitments") == [], "disconnecting Google removes what it brought in")
        api.post("/auth/logout")
        check(api.get("/home", expect=401) is not None, "a signed-out session is refused")
    finally:
        api.token = None


def journey_60_phone_delivery(api: Any, check: Any, run: Any) -> None:
    api.post("/connections/demo")  # the previous journey left this user empty
    token = "ExponentPushToken[functionaltestdevice0]"
    api.post("/devices", {"push_token": token, "platform": "android"})
    api.post("/devices", {"push_token": "nope", "platform": "android"}, expect=422)
    api.post("/notifications/read")  # a new "ready" is only sent once the last one was seen
    brief = api.post("/briefs?period=weekly")
    check(brief["items"], "a brief is made")
    notes = api.get("/notifications")
    check(
        notes and notes[0]["deep_link"] == f"pwm://brief/{brief['id']}",
        "the notification deep-links to that brief",
    )
    check(
        api.get(f"/briefs/{brief['id']}")["id"] == brief["id"],
        "the deep link's brief can be fetched by id",
    )
    api.get("/briefs/00000000-0000-0000-0000-000000000000", expect=404)
    api.call("DELETE", "/devices", {"push_token": token, "platform": "android"})
    api.get("/.well-known/assetlinks.json", expect=404)


def journey_70_beta_readiness(api: Any, check: Any, run: Any) -> None:
    for page in ("privacy", "terms", "subprocessors"):
        status, _ = _hop(f"{api.base}/legal/{page}")
        check(status == 200, f"the {page} page is served publicly")
    ticket = api.post("/me/export")
    path = ticket["url"].split(api.base, 1)[1]
    export = api.get(path)
    check(
        export["format"].startswith("personal-world-model-export") and export["sources"],
        "the export downloads once",
    )
    api.get(path, expect=404)
