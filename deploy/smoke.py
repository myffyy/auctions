"""Verify the staging release through its HTTP interface."""

import json
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener


def verify(revision: str, config_path: Path) -> None:
    config = json.loads(config_path.read_text())
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base = "http://127.0.0.1:18060"

    def request(path: str, data: dict[str, str] | None = None) -> tuple[bytes, str]:
        payload = json.dumps(data).encode() if data is not None else None
        query = Request(base + path, data=payload, headers={"Content-Type": "application/json"})
        with opener.open(query, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"{path}: HTTP {response.status}")
            return response.read(), response.geturl()

    if json.loads(request("/health")[0]) != {"status": "ok"}:
        raise RuntimeError("Unexpected health response")
    if json.loads(request("/version")[0]) != {"revision": revision}:
        raise RuntimeError("The running revision does not match the candidate")

    username = config["username"]
    account = json.loads(
        request("/auth/login", {"username": username, "password": config["password"]})[0]
    )
    if account["username"] != username or request("/app")[1] != base + "/app":
        raise RuntimeError("Staging smoke account could not open the dashboard")
    lots = json.loads(request("/web/lots")[0])
    if not any(lot["id"] == config["lot_id"] for lot in lots):
        raise RuntimeError("The control lot is missing from the staging catalog")


if __name__ == "__main__":
    try:
        verify(sys.argv[1], Path(sys.argv[2]))
    except Exception as error:
        sys.exit(f"Staging HTTP verification failed: {type(error).__name__}: {error}")
