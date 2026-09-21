from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pwm.api.ask import router as ask_router
from pwm.api.auth import router as auth_router
from pwm.api.commitments import router as commitments_router
from pwm.api.connections import router as connections_router
from pwm.api.home import router as home_router
from pwm.api.people import router as people_router
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


async def _provider_unavailable(request: Request, error: Exception) -> JSONResponse:
    # The provider's message can quote the request, which is someone's mail: never pass it on.
    return JSONResponse(
        status_code=503, content={"detail": "The model provider is unavailable. Try again shortly."}
    )


for _error in provider_errors():
    app.add_exception_handler(_error, _provider_unavailable)


@app.get("/health")
def health() -> Health:
    return Health(status="ok")
