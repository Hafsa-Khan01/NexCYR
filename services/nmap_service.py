"""Safe nmap execution.

The target value is strictly validated before it ever reaches subprocess,
arguments are passed as a list (never shell=True), and nmap flags can never
be injected because a value starting with '-' is rejected.
"""

import ipaddress
import logging
import re
import subprocess

from config import Config

logger = logging.getLogger("nexcyr.nmap")

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_TIMEOUT_SECONDS = 120


def is_safe_scan_value(value: str) -> bool:
    """Only plain IPs, FQDNs, hostnames or CIDR networks are scannable."""
    value = (value or "").strip()
    if not value or value.startswith("-"):
        return False

    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass

    try:
        network = ipaddress.ip_network(value, strict=False)
        if network.num_addresses <= 256:
            return True
    except ValueError:
        pass

    if _DOMAIN_RE.match(value) or _HOSTNAME_RE.match(value):
        return True

    return False


def nmap_available() -> bool:
    return Config.resolve_nmap() is not None


def run_nmap(target: str, service_version: bool = True) -> dict:
    """Run a safe, non-destructive nmap scan against a validated target."""
    if not is_safe_scan_value(target):
        return {
            "target": target,
            "status": "rejected",
            "return_code": -1,
            "output": "",
            "error": "Target value is not a safe scannable IP, hostname or small network.",
        }

    nmap_path = Config.resolve_nmap()
    if not nmap_path:
        return {
            "target": target,
            "status": "nmap_unavailable",
            "return_code": -1,
            "output": "",
            "error": (
                "Nmap executable was not found. Install Nmap or set NMAP_PATH. "
                "No scan was performed."
            ),
        }

    args = [nmap_path, "-Pn"]
    if service_version:
        args.append("-sV")
    args.append(target)

    logger.info("Running nmap against %s", target)
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
        return {
            "target": target,
            "status": "completed" if result.returncode == 0 else "failed",
            "return_code": result.returncode,
            "output": result.stdout,
            "error": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "target": target,
            "status": "timeout",
            "return_code": -1,
            "output": "",
            "error": f"Nmap scan timed out after {_TIMEOUT_SECONDS} seconds",
        }
    except OSError as exc:
        logger.warning("Nmap execution failed: %s", exc)
        return {
            "target": target,
            "status": "failed",
            "return_code": -1,
            "output": "",
            "error": f"Nmap could not be executed: {exc}",
        }
