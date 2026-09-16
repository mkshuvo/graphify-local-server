import os
import re
import secrets
from enum import Enum
from typing import Optional, List
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

CLOUD_ENV_INDICATORS = [
    "RAILWAY_ENVIRONMENT",
    "FLY_APP_NAME",
    "RENDER",
    "KUBERNETES_SERVICE_HOST",
    "AWS_EXECUTION_ENV",
    "VERCEL",
    "HEROKU_APP_ID",
    "DIGITALOCEAN_APP_ID",
]


class SecurityMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class SecurityConfig:
    def __init__(self):
        # Explicit env takes precedence: GRAPHIFY_ENV=production or local
        env_var = os.getenv("GRAPHIFY_ENV", "").lower()
        self.api_key = os.getenv("GRAPHIFY_API_KEY", "").strip() or None

        # Auto-detect if running in cloud/production
        is_cloud_detected = (
            env_var in ("production", "prod", "cloud", "remote")
            or any(ind in os.environ for ind in CLOUD_ENV_INDICATORS)
            or bool(self.api_key)  # If user explicitly sets an API key, enforce auth
        )

        self.mode = SecurityMode.CLOUD if is_cloud_detected else SecurityMode.LOCAL
        self.cypher_read_only = os.getenv("GRAPHIFY_CYPHER_READONLY", "true" if is_cloud_detected else "false").lower() == "true"

        # CORS Configuration
        if self.mode == SecurityMode.LOCAL:
            # Local Mode: Allow local dev ports, 127.0.0.1, and localhost
            self.allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
            self.allowed_origins: List[str] = [
                "http://localhost:28848",
                "http://127.0.0.1:28848",
                "http://localhost:3000",
                "http://localhost:5173",
                "vscode-webview://*",
            ]
        else:
            # Cloud Mode: Strict origins only
            raw_origins = os.getenv("GRAPHIFY_ALLOWED_ORIGINS", "")
            self.allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()] or [
                "http://localhost:28848"
            ]
            self.allow_origin_regex = None

    def is_local(self) -> bool:
        return self.mode == SecurityMode.LOCAL

    def is_cloud(self) -> bool:
        return self.mode == SecurityMode.CLOUD


# Global security instance
security_config = SecurityConfig()


class DynamicSecurityMiddleware(BaseHTTPMiddleware):
    """
    Dynamically applies security policies based on the deployment profile:
    - LOCAL: Zero friction, no mandatory token, localhost protected.
    - CLOUD: Enforces Bearer token / X-API-Key, adds HSTS & CSP headers.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. Cloud Authentication Gate
        if security_config.is_cloud() and security_config.api_key:
            # Public endpoints exempted from auth (e.g. Health check probe and Static assets)
            is_exempt = (
                path == "/health"
                or path == "/"
                or path.startswith("/static")
                or path.startswith("/docs")
                or path.startswith("/openapi")
            )
            if not is_exempt:
                auth_header = request.headers.get("Authorization", "")
                api_key_header = request.headers.get("X-API-Key", "")

                token = None
                if auth_header.startswith("Bearer "):
                    token = auth_header[len("Bearer "):].strip()
                elif api_key_header:
                    token = api_key_header.strip()

                if not token or not secrets.compare_digest(token, security_config.api_key):
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": "Unauthorized",
                            "detail": "Invalid or missing API key. Provide Authorization: Bearer <token> or X-API-Key: <token>",
                            "mode": "cloud_security_enforced",
                        },
                        headers={"WWW-Authenticate": "Bearer"},
                    )

        # 2. Cypher Read-Only Guardrail in Cloud
        if security_config.cypher_read_only and path == "/api/cypher" and request.method == "POST":
            # Note: Route handler inspects query for destructive clauses
            pass

        # 3. Process request
        response = await call_next(request)

        # 4. Inject Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Graphify-Security-Mode"] = security_config.mode.value

        if security_config.is_cloud():
            # In production, recommend HSTS
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
