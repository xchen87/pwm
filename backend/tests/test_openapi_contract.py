import json

from pwm.api.export_openapi import TARGET
from pwm.api.main import app


def test_committed_openapi_schema_is_current() -> None:
    """The app's types are generated from this file; a stale copy means a broken contract."""
    assert json.loads(TARGET.read_text(encoding="utf-8")) == app.openapi(), (
        "run `uv run python -m pwm.api.export_openapi` then `npm run gen:api` in app/"
    )
