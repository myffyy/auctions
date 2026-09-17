"""Аутентификация и проверка ролей веб-интерфейса."""

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from auctions.dependencies import DbSession
from auctions.models import Account, AccountRole


def hash_password(password: str, salt: str | None = None) -> str:
    """Вернуть PBKDF2-хеш; открытый пароль в БД не хранится."""

    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt.encode(), 310_000)
    return f"pbkdf2_sha256${actual_salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt, _ = password_hash.split("$", maxsplit=2)
    except ValueError:
        return False
    return algorithm == "pbkdf2_sha256" and hmac.compare_digest(
        hash_password(password, salt), password_hash
    )


def current_account(request: Request, session: DbSession) -> Account:
    account_id = request.session.get("account_id")
    account = session.get(Account, account_id) if isinstance(account_id, int) else None
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    return account


CurrentAccount = Annotated[Account, Depends(current_account)]


def ensure_role(account: Account, *roles: AccountRole) -> None:
    if account.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
