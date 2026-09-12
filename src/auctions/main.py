from fastapi import FastAPI

app = FastAPI(
    title="Auctions API",
    description="HTTP API для учёта аукционов и продаж лотов",
    version="0.1.0",
)


@app.get("/health", tags=["service"])
def health() -> dict[str, str]:
    """Сообщить, что HTTP-приложение работает."""

    return {"status": "ok"}
