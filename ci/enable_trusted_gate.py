"""Require the trusted GitHub Actions gate after its reviewed workflow reaches main."""

import base64
import json
import subprocess  # nosec B404
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
credential = subprocess.run(  # nosec B603 B607
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    text=True,
    capture_output=True,
    check=True,
)
values = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
auth = base64.b64encode(f"{values['username']}:{values['password']}".encode()).decode()
headers = {
    "Authorization": f"Basic {auth}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "auctions-lr5",
}
base = "https://api.github.com/repos/myffyy/auctions"


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path, headers=headers, data=data, method="PATCH" if data else "GET"
    )
    with urllib.request.urlopen(req, timeout=20) as response:  # nosec B310
        return json.load(response)


local = subprocess.check_output(  # nosec B603 B607
    ["git", "hash-object", ".github/workflows/jenkins-gate.yml"], cwd=root, text=True
).strip()
try:
    remote = request("/contents/.github/workflows/jenkins-gate.yml?ref=main")["sha"]
except urllib.error.HTTPError as exc:
    raise SystemExit("Trusted workflow is not available in main yet.") from exc
if local != remote:
    raise SystemExit("Workflow in main differs from the reviewed local version.")
status_path = "/branches/main/protection/required_status_checks"
current = request(status_path)
checks = [
    {"context": item["context"], "app_id": item.get("app_id") or -1} for item in current["checks"]
]
actions = next((item["app_id"] for item in checks if item["context"] == "container-check"), None)
if not actions or actions < 0:
    raise SystemExit("Cannot identify the existing GitHub Actions source.")
checks = [item for item in checks if item["context"] != "jenkins-gate"]
checks.append({"context": "jenkins-gate", "app_id": actions})
result = request(status_path, {"strict": True, "checks": checks})
print("Required checks:", ", ".join(item["context"] for item in result["checks"]))
