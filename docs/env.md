# Environment variables

Backend variables use the `PWM_` prefix and may be placed in a `.env` file at the repo root (gitignored).

| Variable | Default | Purpose |
|---|---|---|
| `PWM_DATABASE_URL` | `postgresql+psycopg://pwm:pwm@localhost:5433/pwm` | SQLAlchemy URL. The default matches `docker-compose.yml`. |
| `PWM_ENVIRONMENT` | `local` | `local`, `staging`, or `production`. |
| `PWM_EXTRACTOR` | `heuristic` | `heuristic` (rule-based extraction, template briefs and answers; no credentials, nothing leaves the machine) or `anthropic` (model-backed extraction, briefs and answers; sends source text to the provider). |
| `PWM_TRIAGE_MODEL` | `claude-haiku-4-5` | Model for the triage stage when `PWM_EXTRACTOR=anthropic`. |
| `PWM_EXTRACTION_MODEL` | `claude-opus-5` | Model for the extraction stage. |
| `PWM_DEV_USER_EMAIL` / `PWM_DEV_USER_NAME` | `alex.rivera@example.com` / `Alex Rivera` | The single local user the API serves until Slice 4 adds authentication. Matches the synthetic fixture. |
| `ANTHROPIC_API_KEY` | unset | Read by the Anthropic SDK itself. Server-side only. |
| `PWM_FIXED_NOW` | unset | Pins the clock (ISO timestamp). `scripts/demo.sh` sets `2026-09-12T09:00:00+00:00`, inside the synthetic mailbox's timeline. Never set in production. |
| `PWM_DEV_LOGIN` | `true` | Serve the local development user to requests without a session. Only ever honoured when `PWM_ENVIRONMENT=local`. |
| `PWM_SESSION_DAYS` | `30` | Session lifetime. |
| `PWM_GOOGLE_CLIENT_ID` / `PWM_GOOGLE_CLIENT_SECRET` | unset | Google OAuth client (type: Web application). Unset means Google is shown as unavailable. Server-side only. |
| `PWM_PUBLIC_URL` | `http://localhost:8000` | Public address of this API. The OAuth redirect URI registered with Google must be `<PWM_PUBLIC_URL>/auth/google/callback`. |
| `PWM_APP_REDIRECTS` | `["pwm://auth","http://localhost:8081/auth","exp://"]` | Where the app may be sent after sign-in. Anything else is refused. |
| `PWM_DATA_KEY` | unset | Base64 of 32 random bytes; encrypts refresh tokens and message bodies. Required before Google can be used. Generate: `python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`. **Losing it makes stored tokens and bodies unreadable; leaking it undoes the encryption.** Keep it out of the database and out of the repo. |
| `PWM_BACKFILL_DAYS` | `90` | How far back the first sync reads. |
| `PWM_GOOGLE_AUTH_URL`, `_TOKEN_URL`, `_REVOKE_URL`, `_USERINFO_URL`, `_API_URL` | Google's | Overridden only to point at the stand-in (`pwm.devtools.fake_google`). |
| `PWM_CORS_ORIGINS` | `["http://localhost:8081","http://localhost:19006"]` | JSON list of web origins allowed to call the API. |

App variables are read by Expo at build time. Anything prefixed `EXPO_PUBLIC_` is compiled into the app bundle and is visible to anyone who has the app: never put a secret in one.

| Variable | Default | Purpose |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the backend. An Android emulator reaches the host machine at `http://10.0.2.2:8000`; a physical phone needs the machine's LAN address. |

Not yet used: push credentials (Slice 5). None of these will ever be `EXPO_PUBLIC_`.
