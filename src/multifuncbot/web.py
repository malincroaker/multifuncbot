"""Optional Mini App server: `multifuncbot-web`. Bot-only installs do not import this."""

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError


def create_app(settings=None):
    settings = settings or Settings.from_env()
    if "shop" not in settings.enabled_modules:
        raise ValueError("Enable shop to run the Mini App server")
    from multifuncbot.modules.shop.api import create_router

    app = FastAPI(title="Multifuncbot Mini App", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database_path = settings.database_path
    public_url = urlsplit(settings.mini_app_url)

    @app.middleware("http")
    async def security(request: Request, call_next):
        # HTTPS tunnels may forward plain HTTP without standard proxy headers.
        # Only restore HTTPS for the explicitly configured public authority.
        if public_url.netloc and request.headers.get("host") == public_url.netloc:
            request.scope["scheme"] = public_url.scheme
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if (origin and origin != expected) or request.headers.get("X-Multifuncbot") != "1":
                return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
            try:
                if int(request.headers.get("content-length", "0")) > 16384:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"detail": {"ru": error.ru, "en": error.en}}, status_code=409)

    @app.get("/health")
    def health():
        return {"status": "ok", "payment_provider": "demo"}

    app.include_router(create_router(Database(settings.database_path), settings))
    static = Path(__file__).parent / "modules" / "shop" / "static"
    app.mount("/", StaticFiles(directory=static, html=True), name="shop")
    return app


def main():
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
