"""End-to-end functional test against a real server and a real database.

Starts from an empty `pwm_functional` database, applies migrations, loads the synthetic
mailbox through the CLI, starts uvicorn, and drives the product's user journeys over
HTTP exactly as the app does. Run by scripts/verify.sh.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
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
    def __init__(self, base: str) -> None:
        self.base = base

    def call(self, method: str, path: str, body: Any = None, expect: int = 200) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers={"Content-Type": "application/json"}
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


def main() -> None:
    recreate_database()
    run("uv", "run", "alembic", "upgrade", "head")
    first = run("uv", "run", "python", "-m", "pwm.cli", "demo")
    check("ingested 122 new sources" in first, "demo ingests the synthetic mailbox")
    second = run("uv", "run", "python", "-m", "pwm.cli", "demo")
    check("ingested 0 new sources" in second, "loading the same mailbox again ingests nothing")

    port = free_port()
    server = subprocess.Popen(
        ["uv", "run", "uvicorn", "pwm.api.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=ENV,
    )  # fmt: skip
    try:
        api = Api(f"http://127.0.0.1:{port}")
        for _ in range(60):
            try:
                urllib.request.urlopen(api.base + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            sys.exit("server did not start")
        journeys(api)
    finally:
        server.terminate()
        server.wait(timeout=10)
    print(f"functional: {len(CHECKS)} checks passed")


if __name__ == "__main__":
    main()
