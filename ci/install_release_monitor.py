"""Install a user LaunchAgent that runs the reviewed release gate on main changes."""

import os
import plistlib
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("LaunchAgent installation is supported on macOS only.")
root = Path(__file__).resolve().parent.parent
source_private = root / "ci" / ".secrets"
if not (source_private / "registry-password").is_file():
    raise SystemExit("Run python3 ci/init_registry.py first.")
plist = Path.home() / "Library/LaunchAgents/com.auctions.lr5.release.plist"
if plist.exists():
    raise SystemExit("Release monitor plist already exists; inspect it before replacing it.")
runtime = Path.home() / "Library/Application Support/AuctionsLR5"
private = runtime / "ci" / ".secrets"
private.mkdir(mode=0o700, parents=True, exist_ok=True)
shutil.copyfile(source_private / "registry-password", private / "registry-password")
(private / "registry-password").chmod(0o600)
state = private / "release-last-attempt"
if not state.exists():
    remote = subprocess.check_output(  # nosec B603 B607
        ["git", "ls-remote", "https://github.com/myffyy/auctions.git", "refs/heads/main"],
        text=True,
        env=os.environ | {"GIT_TERMINAL_PROMPT": "0"},
    ).split()[0]
    if len(remote) != 40 or any(char not in "0123456789abcdef" for char in remote):
        raise SystemExit("Cannot determine main SHA.")
    state.write_text(remote + "\n")
    state.chmod(0o600)
for name, target in (
    ("release.sh", "trusted-release.sh"),
    ("release-daemon.sh", "release-daemon.sh"),
):
    destination = private / target
    shutil.copyfile(root / "ci" / name, destination)
    destination.chmod(0o700)
(runtime / "ci").mkdir(parents=True, exist_ok=True)
shutil.copyfile(root / "ci/enable_trusted_gate.py", runtime / "ci/enable_trusted_gate.py")
workflow = runtime / ".github/workflows/jenkins-gate.yml"
workflow.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(root / ".github/workflows/jenkins-gate.yml", workflow)
reports = runtime / "reports"
reports.mkdir(exist_ok=True)
plist.parent.mkdir(parents=True, exist_ok=True)
config = {
    "Label": "com.auctions.lr5.release",
    "ProgramArguments": ["/bin/bash", str(private / "release-daemon.sh")],
    "WorkingDirectory": str(runtime),
    "EnvironmentVariables": {
        "PATH": os.environ.get(
            "PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        ),
        "AUCTIONS_CI_ROOT": str(runtime),
        "GIT_TERMINAL_PROMPT": "0",
    },
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": str(reports / "release-monitor.log"),
    "StandardErrorPath": str(reports / "release-monitor-error.log"),
}
with plist.open("xb") as file:
    plistlib.dump(config, file)
subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], check=True)  # nosec B603 B607
print("Release monitor installed. It starts with the next change to main.")
