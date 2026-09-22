"""The two files that let a phone trust https://<our domain>/auth as ours, so sign-in can
come back over a claimed HTTPS link instead of a custom scheme anyone can register
(decisions D69). Served only when the identities are configured; 404 otherwise."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from pwm.config import get_settings

router = APIRouter()


@router.get("/.well-known/apple-app-site-association")
def apple() -> JSONResponse:
    settings = get_settings()
    if not settings.apple_app_id:
        raise HTTPException(404)
    return JSONResponse(
        {
            "applinks": {
                "apps": [],
                "details": [
                    {"appID": settings.apple_app_id, "paths": ["/auth", "/brief/*", "/assertion/*"]}
                ],
            }
        },
        media_type="application/json",
    )


@router.get("/.well-known/assetlinks.json")
def android() -> JSONResponse:
    settings = get_settings()
    if not (settings.android_package and settings.android_cert_fingerprints):
        raise HTTPException(404)
    return JSONResponse(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.android_package,
                    "sha256_cert_fingerprints": settings.android_cert_fingerprints,
                },
            }
        ]
    )
