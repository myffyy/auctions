"""Create local registry credentials once without printing the password."""

import os
import secrets
import subprocess  # nosec B404
from pathlib import Path

root = Path(__file__).resolve().parent / ".secrets"
root.mkdir(mode=0o700, exist_ok=True)
password_path = root / "registry-password"
hash_path = root / "htpasswd"
if password_path.exists() or hash_path.exists():
    if password_path.is_file() and hash_path.is_file():
        print("Registry credentials already exist.")
        raise SystemExit(0)
    raise SystemExit("Incomplete registry credentials; inspect ci/.secrets before retrying.")
password = secrets.token_urlsafe(32)
result = subprocess.run(  # nosec B603 B607
    ["htpasswd", "-nBi", "ci"],
    input=password + "\n",
    text=True,
    capture_output=True,
    check=True,
)
for path, content in ((password_path, password + "\n"), (hash_path, result.stdout)):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(content)
print("Registry credentials created in ci/.secrets.")
