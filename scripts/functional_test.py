"""End-to-end functional test against a real server and a real database.

Starts from an empty `pwm_functional` database, applies migrations, loads the synthetic
mailbox through the CLI, starts uvicorn, and drives the product's user journeys over
HTTP exactly as the app does. Run by scripts/verify.sh.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("PWM_TEST_ADMIN_URL", "postgresql+psycopg://pwm:pwm@localhost:5433/pwm")
DB_URL = ADMIN_URL.rsplit("/", 1)[0] + "/pwm_functional"
# The synthetic mailbox lives in September 2026; the demo clock is pinned there.
ENV = {
    **os.environ,
    "PWM_DATABASE_URL": DB_URL,
    "PWM_EXTRACTOR": "heuristic",
    "PWM_ENVIRONMENT": "local",
    "PWM_PUSH_URL": "",  # never Expo's real push service from a test
    "PWM_FIXED_NOW": "2026-09-12T09:00:00+00:00",
}
CHECKS: list[str] = []


def run(*command: str) -> str:
    done = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, text=True, check=False)
    if done.returncode:
        sys.exit(f"FAILED: {' '.join(command)}\n{done.stdout}\n{done.stderr}")
    return done.stdout


def check(condition: bool, what: str) -> None:
    if not condition:
        sys.exit(f"FUNCTIONAL TEST FAILED: {what}")
    CHECKS.append(what)


def recreate_database() -> None:
    from sqlalchemy import create_engine, text

    with create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT").connect() as admin:
        admin.execute(text("drop database if exists pwm_functional with (force)"))
        admin.execute(text("create database pwm_functional"))


class Api:
    def __init__(self, base: str, google: str = "") -> None:
        self.base = base
        self.google = google  # the fake Google this server was pointed at
        self.token: str | None = None  # when set, requests are made as that signed-in user

    def call(self, method: str, path: str, body: Any = None, expect: int = 200) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        check(status == expect, f"{method} {path} -> {expect} (got {status})")
        return json.loads(payload) if payload else None

    def get(self, path: str, expect: int = 200) -> Any:
        return self.call("GET", path, expect=expect)

    def post(self, path: str, body: Any = None, expect: int = 200) -> Any:
        return self.call("POST", path, body if body is not None else {}, expect=expect)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def journeys(api: Api) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import journeys as steps  # noqa: PLC0415 - loaded after the server is up

    for name in sorted(n for n in dir(steps) if n.startswith("journey_")):
        getattr(steps, name)(api, check, run)


def browser() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if path := shutil.which(name):
            return path
    return None


def rendered(chrome: str, url: str) -> str:
    done = subprocess.run(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=390,844",
         "--virtual-time-budget=20000", "--dump-dom", url],
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    return done.stdout


def app_in_a_browser(api: Api, static_port: int) -> None:
    """Build the real web app against this server and look at what a person would see.

    `--clear` matters: Metro caches transformed files with EXPO_PUBLIC_* values inlined, so
    without it the bundle would still point at whatever API URL an earlier build used.
    """
    build = subprocess.run(
        ["npx", "expo", "export", "--platform", "web", "--clear"], cwd=ROOT / "app",
        capture_output=True, text=True, check=False,
        env={**os.environ, "CI": "1", "EXPO_PUBLIC_API_URL": api.base},
    )  # fmt: skip
    check(
        build.returncode == 0 and (ROOT / "app/dist/index.html").exists(),
        "the production web build succeeds",
    )
    chrome = browser()
    if chrome is None:
        if os.environ.get("PWM_REQUIRE_BROWSER"):
            sys.exit(
                "FUNCTIONAL TEST FAILED: PWM_REQUIRE_BROWSER is set and no Chrome/Chromium was found"
            )
        print("functional: WARNING no Chrome/Chromium found; in-browser checks were NOT run")
        return
    static = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/spa_server.py"), str(ROOT / "app/dist"), str(static_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        time.sleep(1)
        check(static.poll() is None, "the static server for the built app is running")
        page = f"http://127.0.0.1:{static_port}/"
        api.call("DELETE", "/me")
        check(
            "Connect your life" in rendered(chrome, page),
            "a new user sees onboarding in the browser",
        )

        # A real browser clicks "Continue with Google" and is carried through the stand-in
        # for Google and back, redeeming the login code with the secret it kept.
        with tempfile.TemporaryDirectory() as profile:
            driven = subprocess.run(
                ["node", str(ROOT / "scripts/signin_e2e.mjs"), page, chrome, profile],
                capture_output=True, text=True, timeout=240, check=False,
            )  # fmt: skip
        outcome = (
            json.loads(driven.stdout.strip().splitlines()[-1]) if driven.stdout.strip() else {}
        )
        check(
            outcome.get("clicked") is True, "in a browser: the Google button is there and clickable"
        )
        check(
            outcome.get("signedIn") is True,
            "in a browser: sign-in completes and returns to the app",
        )
        check(
            outcome.get("verifierCleared") is True,
            "in a browser: the sign-in secret is used once and removed",
        )
        check(
            outcome.get("tokenNotInUrl") is True,
            "in a browser: the session token never appears in a URL",
        )
        check(
            outcome.get("accountShown") is True,
            "in a browser: Settings shows the signed-in Google account",
        )

        api.call("DELETE", "/me")
        api.post("/connections/demo")
        home = rendered(chrome, page)
        check(
            "What changed" in home and "Needs attention" in home,
            "after connecting, the browser shows Your World",
        )
        check("$19,950" in home, "the home screen shows a real change with a readable amount")
        check("It looks like" in home, "unconfirmed changes are hedged on screen")
    finally:
        static.terminate()
        static.wait(timeout=10)


def main() -> None:
    recreate_database()
    run("uv", "run", "alembic", "upgrade", "head")
    first = run("uv", "run", "python", "-m", "pwm.cli", "demo")
    check("ingested 122 new sources" in first, "demo ingests the synthetic mailbox")
    second = run("uv", "run", "python", "-m", "pwm.cli", "demo")
    check("ingested 0 new sources" in second, "loading the same mailbox again ingests nothing")

    port, static_port, google_port = free_port(), free_port(), free_port()
    google = f"http://127.0.0.1:{google_port}"
    # Slice 4 runs against a stand-in for Google, as a real separate server.
    ENV.update(
        {
            "PWM_GOOGLE_CLIENT_ID": "functional-client",
            "PWM_GOOGLE_CLIENT_SECRET": "functional-secret",
            "PWM_DATA_KEY": base64.b64encode(os.urandom(32)).decode(),
            "PWM_PUBLIC_URL": f"http://127.0.0.1:{port}",
            "PWM_GOOGLE_AUTH_URL": f"{google}/o/oauth2/v2/auth",
            "PWM_GOOGLE_TOKEN_URL": f"{google}/token",
            "PWM_GOOGLE_REVOKE_URL": f"{google}/revoke",
            "PWM_GOOGLE_USERINFO_URL": f"{google}/v1/userinfo",
            "PWM_GOOGLE_API_URL": google,
        }
    )
    fake_google = subprocess.Popen(
        ["uv", "run", "uvicorn", "pwm.devtools.fake_google:app", "--port", str(google_port), "--log-level", "warning"],
        cwd=ROOT, env=ENV,
    )  # fmt: skip
    server_env = {
        **ENV,
        "PWM_CORS_ORIGINS": f'["http://127.0.0.1:{static_port}"]',
        "PWM_APP_REDIRECTS": f'["pwm://auth", "http://127.0.0.1:{static_port}/auth"]',
    }
    server = subprocess.Popen(
        ["uv", "run", "uvicorn", "pwm.api.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=server_env,
    )  # fmt: skip
    try:
        api = Api(f"http://127.0.0.1:{port}", google)
        for _ in range(60):
            try:
                urllib.request.urlopen(api.base + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            sys.exit("server did not start")
        journeys(api)
        app_in_a_browser(api, static_port)
    finally:
        for process in (server, fake_google):
            process.terminate()
            process.wait(timeout=10)
    print(f"functional: {len(CHECKS)} checks passed")


if __name__ == "__main__":
    main()
