from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pwm import crypto
from pwm.api.ask import router as ask_router
from pwm.api.auth import router as auth_router
from pwm.api.commitments import router as commitments_router
from pwm.api.connections import router as connections_router
from pwm.api.devices import router as devices_router
from pwm.api.home import router as home_router
from pwm.api.people import router as people_router
from pwm.api.wellknown import router as wellknown_router
from pwm.config import get_settings
from pwm.extraction.factory import provider_errors


class Health(BaseModel):
    status: str


app = FastAPI(title="Personal World Model API", version="0.0.1")

# The Expo web build runs on a different origin from the API during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(commitments_router)
app.include_router(home_router)
app.include_router(ask_router)
app.include_router(connections_router)
app.include_router(people_router)
app.include_router(devices_router)
app.include_router(wellknown_router)


async def _provider_unavailable(request: Request, error: Exception) -> JSONResponse:
    # The provider's message can quote the request, which is someone's mail: never pass it on.
    return JSONResponse(
        status_code=503, content={"detail": "The model provider is unavailable. Try again shortly."}
    )


async def _unreadable(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Stored data cannot be read right now. Nothing has been lost."},
    )


# A missing or rotated data key must not look like a crash, and must not change anything.
app.add_exception_handler(crypto.DataKeyMissing, _unreadable)
app.add_exception_handler(crypto.Undecryptable, _unreadable)

for _error in provider_errors():
    app.add_exception_handler(_error, _provider_unavailable)


@app.get("/health")
def health() -> Health:
    return Health(status="ok")
