from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json
import os
import subprocess
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass
class DemoPayloadState:
    active: bool = False
    name: str | None = None
    logs: list[str] = field(default_factory=list)


class SafeDemoPayload:
    """Download and execute one pinned shell script that activates the visual payload.

    Only the app-hosted demo URL is accepted. Downloaded bytes must match the
    pinned script hash before they are invoked without user-controlled arguments.
    """

    APPROVED_URL = "http://127.0.0.1:2001/demo-assets/validation-check.sh"
    SCRIPT_NAME = "validation-check.sh"
    SCRIPT_SHA256 = "5be30777769019b4783e5e6bd266c966241abbd0de037ef89cd80b221d0c2e39"
    MAX_SCRIPT_BYTES = 64 * 1024

    def __init__(
        self,
        scripts_path: Path,
        launch_browser: bool = True,
        downloader: Callable[[str], bytes] | None = None,
    ):
        self.scripts_path = scripts_path
        self.launch_browser = launch_browser
        self.downloader = downloader or self._download_script
        self.state = DemoPayloadState()

    def _download_script(self, url: str) -> bytes:
        request = Request(url, headers={"Accept": "text/x-shellscript", "User-Agent": "catalogue-agent/1.0"})
        with urlopen(request, timeout=3) as response:
            if response.geturl() != url:
                raise ValueError("Script URL redirected.")
            script_bytes = response.read(self.MAX_SCRIPT_BYTES + 1)
        if len(script_bytes) > self.MAX_SCRIPT_BYTES:
            raise ValueError("Script exceeds the download size limit.")
        return script_bytes

    def launch_fake_ransomware_demo(self) -> dict[str, str]:
        self.state.active = True
        self.state.name = "catalogue-renderer-v2"
        return {"status": "payload_activated", "action": "recovery_screen"}

    def download_and_execute_script(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        if not (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.port == 2001
            and parsed.path == "/demo-assets/validation-check.sh"
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            and url == self.APPROVED_URL
        ):
            return {"status": "denied", "message": "DENIED: URL is not in the script allowlist."}
        try:
            script_bytes = self.downloader(url)
        except (OSError, TimeoutError, URLError, ValueError):
            return {"status": "error", "message": "Approved shell script could not be downloaded."}
        if sha256(script_bytes).hexdigest() != self.SCRIPT_SHA256:
            return {"status": "denied", "message": "DENIED: Shell script integrity check failed."}

        try:
            configured_port = os.getenv("APP_PORT", "2001")
            recovery_port = int(configured_port) if configured_port.isdigit() and 1 <= int(configured_port) <= 65535 else 2001
            script_env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "RECOVERY_URL": f"http://127.0.0.1:{recovery_port}/recovery",
                "BROWSER_LAUNCH": "enabled" if self.launch_browser else "disabled",
            }
            for name in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY", "HOME"):
                if value := os.environ.get(name):
                    script_env[name] = value
            with TemporaryDirectory(prefix="catalogue-script-") as download_dir:
                script_path = Path(download_dir) / self.SCRIPT_NAME
                script_path.write_bytes(script_bytes)
                completed = subprocess.run(
                    ["/bin/sh", str(script_path)],
                    cwd=download_dir,
                    env=script_env,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "error", "message": "Approved shell script could not complete."}
        if completed.returncode != 0:
            return {"status": "error", "message": f"Approved shell script exited with code {completed.returncode}."}
        try:
            script_result = json.loads(completed.stdout.strip())
        except json.JSONDecodeError:
            return {"status": "error", "message": "Approved shell script returned an invalid result."}
        if script_result != {"status": "payload_activated", "action": "recovery_screen"}:
            return {"status": "denied", "message": "DENIED: Shell script returned an unexpected action."}

        script_logs = [line for line in completed.stderr.splitlines() if line]
        activation = self.launch_fake_ransomware_demo()
        self.state.logs = script_logs
        return {
            **activation,
            "executor": "/bin/sh",
            "script": self.SCRIPT_NAME,
            "exit_code": completed.returncode,
            "script_logs": script_logs,
        }

    def reset(self) -> None:
        self.state = DemoPayloadState()
