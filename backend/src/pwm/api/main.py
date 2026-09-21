from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pwm.api.commitments import router as commitments_router
from pwm.api.home import router as home_router
from pwm.config import get_settings


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

app.include_router(commitments_router)
app.include_router(home_router)


@app.get("/health")
def health() -> Health:
    return Health(status="ok")
