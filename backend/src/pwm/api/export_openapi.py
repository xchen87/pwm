"""Write the OpenAPI schema the app's TypeScript types are generated from.

Run:  uv run python -m pwm.api.export_openapi
"""

import json
from pathlib import Path

from pwm.api.main import app

TARGET = Path(__file__).resolve().parents[4] / "app" / "src" / "api" / "openapi.json"

if __name__ == "__main__":
    TARGET.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {TARGET}")
