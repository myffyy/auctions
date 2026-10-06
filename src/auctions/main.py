from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auctions.config import get_settings
from auctions.routers.catalog import router as catalog_router
from auctions.routers.participants import router as participants_router
from auctions.routers.sales import router as sales_router
from auctions.routers.web import router as web_router

app = FastAPI(
    title="Auctions API",
    description="HTTP API для учёта аукционов и продаж лотов",
    version="0.1.0",
)

app.add_middleware(
    SessionMiddleware, secret_key=get_settings().session_secret, same_site="lax", https_only=False
)
app.mount("/static", StaticFiles(directory="src/auctions/static"), name="static")

app.include_router(participants_router)
app.include_router(catalog_router)
app.include_router(sales_router)
app.include_router(web_router)


@app.middleware("http")
async def redirect_unauthenticated_pages(request: Request, call_next):
    """При открытии защищённого адреса в браузере показать страницу входа."""

    response = await call_next(request)
    if (
        request.method == "GET"
        and response.status_code == 401
        and "text/html" in request.headers.get("accept", "")
    ):
        return RedirectResponse("/login", status_code=303)
    return response


@app.get("/health", tags=["service"])
def health() -> dict[str, str]:
    """Сообщить, что HTTP-приложение работает."""

    return {"status": "ok"}
