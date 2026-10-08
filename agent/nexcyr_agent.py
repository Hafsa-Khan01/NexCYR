"""NexCYR local Agent runner.

Run this on an authorized Windows/Linux/macOS machine inside the target network.
The Agent polls the NexCYR Cloud for structured jobs only, executes a fixed
allowlist of safe Nmap profiles, reports structured results, and publishes a
passive Wi-Fi snapshot in heartbeats.

Example:
  python agent/nexcyr_agent.py --server https://magnificent-achievement-production.up.railway.app --token "<ONE_TIME_TOKEN>"
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import platform
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

LOG = logging.getLogger("nexcyr.agent")
NMAP_TIMEOUT_SECONDS = 180
POLL_SECONDS = 3
HEARTBEAT_SECONDS = 30


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_capture(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def find_nmap() -> str | None:
    direct = shutil.which("nmap")
    if direct:
        return direct
    if sys.platform.startswith("win"):
        for candidate in (
            r"C:\Program Files\Nmap\nmap.exe",
            r"C:\Program Files (x86)\Nmap\nmap.exe",
        ):
            if Path(candidate).is_file():
                return candidate
    return None


def parse_first_ipv4(text: str) -> str | None:
    for value in re.findall(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", text):
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError:
            continue
    return None


def local_network() -> str | None:
    if platform.system().lower() == "windows":
        code, out, _ = run_capture(["ipconfig"], timeout=10)
        if code != 0:
            return None
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if "IPv4" not in line and "ipv4" not in line:
                continue
            ip = parse_first_ipv4(line)
            if not ip:
                continue
            for nxt in lines[i + 1 : i + 5]:
                if "Subnet Mask" in nxt or "subnet mask" in nxt:
                    mask = parse_first_ipv4(nxt)
                    if mask:
                        try:
                            iface = ipaddress.ip_interface(f"{ip}/{mask}")
                            return str(iface.network)
                        except ValueError:
                            pass
        return None

    # Linux/macOS: use the route-selected interface and its address when
    # available. Fall back to a private /24 only when the OS command is not
    # informative; this is advisory telemetry, not an authorization decision.
    if platform.system().lower() == "linux":
        code, out, _ = run_capture(["ip", "-4", "route", "get", "1.1.1.1"], timeout=10)
        if code == 0:
            ip = parse_first_ipv4(out)
            if ip:
                try:
                    return str(ipaddress.ip_network(f"{ip}/24", strict=False))
                except ValueError:
                    return None

    if platform.system().lower() == "darwin":
        code, out, _ = run_capture(["ifconfig"], timeout=10)
        if code == 0:
            ip = parse_first_ipv4(out)
            if ip:
                try:
                    return str(ipaddress.ip_network(f"{ip}/24", strict=False))
                except ValueError:
                    return None
    return None


def wifi_snapshot() -> dict:
    system = platform.system().lower()
    if system != "windows":
        return {
            "available": False,
            "interface": None,
            "current_ssid": None,
            "local_network": local_network(),
            "networks": [],
            "reason": "The bundled passive Wi-Fi collector currently uses Windows netsh.",
            "captured_at": utc_now(),
        }

    code_i, interfaces, err_i = run_capture(
        ["netsh", "wlan", "show", "interfaces"], timeout=15
    )
    code_n, networks_raw, err_n = run_capture(
        ["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=20
    )
    interface = None
    current_ssid = None

    for line in interfaces.splitlines():
        s = line.strip()
        if s.lower().startswith("name") and ":" in s:
            interface = s.split(":", 1)[1].strip()
        elif s.lower().startswith("ssid") and ":" in s and "bssid" not in s.lower():
            current_ssid = s.split(":", 1)[1].strip()

    observations: list[dict] = []
    current: dict | None = None

    for raw in networks_raw.splitlines():
        line = raw.strip()
        m = re.match(r"SSID\s+\d+\s*:\s*(.*)$", line, re.I)
        if m:
            current = {
                "ssid": m.group(1).strip()[:255],
                "authentication": "Unknown",
                "encryption": "",
                "cipher": "",
                "channel": "",
                "signal": "",
                "bssid": "",
            }
            observations.append(current)
            continue

        if current is None:
            continue

        fields = (
            ("authentication", r"Authentication\s*:\s*(.*)$"),
            ("encryption", r"Encryption\s*:\s*(.*)$"),
            ("cipher", r"Encryption\s*:\s*(.*)$"),
            ("channel", r"Channel\s*:\s*(.*)$"),
            ("signal", r"Signal\s*:\s*(.*)$"),
            ("bssid", r"BSSID\s+\d+\s*:\s*(.*)$"),
        )
        for key, pattern in fields:
            m = re.match(pattern, line, re.I)
            if m:
                current[key] = m.group(1).strip()[:255]
                break

    # Avoid returning a fake "available" state if Windows has no WLAN data.
    available = bool(interface or observations)
    reason = "Passive Wi-Fi snapshot collected by local NexCYR Agent."
    if not available:
        reason = err_i.strip() or err_n.strip() or "No Wi-Fi interface or visible networks."

    return {
        "available": available,
        "interface": interface,
        "current_ssid": current_ssid,
        "local_network": local_network(),
        "networks": observations[:200],
        "reason": reason[:500],
        "captured_at": utc_now(),
    }


def parse_nmap_xml(xml_text: str) -> dict:
    hosts: list[dict] = []
    services: list[dict] = []

    root = ET.fromstring(xml_text)
    for host in root.findall("host"):
        status = host.find("status")
        state = status.get("state", "unknown") if status is not None else "unknown"
        addresses = host.findall("address")
        ipv4 = next(
            (a.get("addr") for a in addresses if a.get("addrtype") == "ipv4"),
            None,
        )
        hostname = ""
        hn = host.find("./hostnames/hostname")
        if hn is not None:
            hostname = hn.get("name") or ""

        if ipv4 and state == "up":
            hosts.append({"address": ipv4, "state": "up", "hostname": hostname})

        for port in host.findall("./ports/port"):
            port_id = port.get("portid")
            try:
                number = int(port_id)
            except (TypeError, ValueError):
                continue
            state_el = port.find("state")
            service_el = port.find("service")
            services.append(
                {
                    "port": number,
                    "state": state_el.get("state") if state_el is not None else "unknown",
                    "service": (service_el.get("name") if service_el is not None else "") or "unknown",
                    "version": (
                        " ".join(
                            x for x in (
                                service_el.get("product") if service_el is not None else "",
                                service_el.get("version") if service_el is not None else "",
                            ) if x
                        )
                    )[:120],
                    "host": ipv4,
                }
            )

    return {"hosts": hosts[:1024], "services": services[:500]}


def nmap_job(job_type: str, target: str, ports_profile: str = "safe_default") -> dict:
    nmap = find_nmap()
    if not nmap:
        raise RuntimeError("Nmap executable not found on this Agent.")

    target = (target or "").strip()
    if not target:
        raise ValueError("Job target is empty.")

    if job_type == "NMAP_HOST_DISCOVERY":
        args = [nmap, "-sn", "-oX", "-", target]
    elif job_type == "NMAP_PORT_SCAN":
        args = [nmap, "-Pn", "-sT", "--top-ports", "100", "--open", "-oX", "-", target]
    elif job_type == "NMAP_SERVICE_ENUMERATION":
        args = [nmap, "-Pn", "-sT", "-sV", "--top-ports", "100", "--open", "-oX", "-", target]
    else:
        raise ValueError(f"Unsupported Nmap job type: {job_type}")

    LOG.info("Executing allowlisted Nmap profile %s against authorized target %s", job_type, target)
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    while proc.poll() is None:
        if time.monotonic() - started > NMAP_TIMEOUT_SECONDS:
            proc.kill()
            proc.wait(timeout=10)
            raise RuntimeError(f"Nmap job exceeded {NMAP_TIMEOUT_SECONDS} second timeout.")
        time.sleep(2)

    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError((stderr or "Nmap returned a non-zero exit code.")[:2000])

    parsed = parse_nmap_xml(stdout)
    return {
        "hosts": parsed["hosts"],
        "services": parsed["services"],
        "ports": [s["port"] for s in parsed["services"] if s.get("state") == "open"],
    }


class NexCYRAgent:
    def __init__(self, server: str, token: str, interval: int):
        self.server = server.rstrip("/")
        self.token = token
        self.interval = max(2, interval)
        self.session = requests.Session()
        self.session.headers.update({
            "X-NexCYR-Agent-Token": token,
            "Accept": "application/json",
        })

    def post(self, path: str, payload: dict) -> dict:
        response = self.session.post(
            f"{self.server}{path}",
            json=payload,
            timeout=30,
        )
        if response.status_code == 401:
            raise RuntimeError("Agent credential rejected or revoked.")
        response.raise_for_status()
        return response.json()

    def get(self, path: str) -> dict:
        response = self.session.get(
            f"{self.server}{path}",
            timeout=30,
        )
        if response.status_code == 401:
            raise RuntimeError("Agent credential rejected or revoked.")
        response.raise_for_status()
        return response.json()

    def capabilities(self) -> dict:
        nmap = bool(find_nmap())
        wifi = wifi_snapshot()
        return {
            "nmap": nmap,
            "host_discovery": nmap,
            "port_scan": nmap,
            "service_enumeration": nmap,
            "wifi": bool(wifi.get("available")),
        }

    def identity_payload(self) -> dict:
        wifi = wifi_snapshot()
        return {
            "hostname": platform.node(),
            "platform": platform.system(),
            "os_info": platform.platform()[:120],
            "arch": platform.machine(),
            "version": "1.0.0-agent",
            "capabilities": self.capabilities(),
            "uptime": "running",
            "wifi_snapshot": wifi,
        }

    def register(self) -> dict:
        payload = self.post("/api/agents/register", self.identity_payload())
        LOG.info(
            "Registered Agent %s (%s) · Nmap=%s · Wi-Fi=%s",
            payload.get("name"),
            payload.get("agent_key"),
            payload.get("nmap_available"),
            payload.get("capabilities", {}).get("wifi"),
        )
        return payload

    def heartbeat(self) -> dict:
        wifi = wifi_snapshot()
        return self.post(
            "/api/agents/heartbeat",
            {
                "version": "1.0.0-agent",
                "capabilities": self.capabilities(),
                "uptime": "running",
                "wifi_snapshot": wifi,
            },
        )

    def next_job(self) -> dict | None:
        payload = self.get("/api/agents/me/jobs/next")
        return payload.get("job")

    def submit(self, job_id: int, status: str, results: dict | None = None, error: str | None = None):
        return self.post(
            f"/api/agents/jobs/{job_id}/result",
            {
                "status": status,
                "results": results or {},
                "error": error,
            },
        )

    def execute(self, job: dict):
        job_id = int(job["id"])
        job_type = str(job.get("job_type") or "")
        params = job.get("params") or {}
        target = str(job.get("target") or params.get("target") or "").strip()

        if not job.get("target_authorized"):
            raise PermissionError("Server refused execution because the target is not authorized.")

        if job_type == "WIFI_DISCOVERY":
            return {
                "wifi_networks": wifi_snapshot().get("networks") or [],
                "wifi_interface": wifi_snapshot().get("interface"),
                "local_network": wifi_snapshot().get("local_network"),
            }

        return nmap_job(
            job_type,
            target,
            str(params.get("ports_profile") or "safe_default"),
        )

    def run(self):
        self.register()
        last_heartbeat = 0.0

        while True:
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                self.heartbeat()
                last_heartbeat = now

            job = self.next_job()
            if not job:
                time.sleep(self.interval)
                continue

            job_id = int(job["id"])
            LOG.info("Claimed job #%s · %s", job_id, job.get("job_type"))
            try:
                results = self.execute(job)
                self.submit(job_id, "completed", results=results)
                LOG.info("Completed job #%s", job_id)
            except Exception as exc:
                LOG.exception("Job #%s failed", job_id)
                try:
                    self.submit(job_id, "failed", error=str(exc)[:2000])
                except Exception:
                    LOG.exception("Could not report failure for job #%s", job_id)

            # Refresh the heartbeat after every job so long-running scans
            # immediately make the Agent appear healthy again.
            try:
                self.heartbeat()
                last_heartbeat = time.monotonic()
            except Exception:
                LOG.exception("Heartbeat failed after job completion")


def main() -> int:
    parser = argparse.ArgumentParser(description="NexCYR local authorized Agent")
    parser.add_argument(
        "--server",
        required=True,
        help="NexCYR Cloud base URL, e.g. https://magnificent-achievement-production.up.railway.app",
    )
    parser.add_argument("--token", required=True, help="One-time NexCYR Agent enrollment token")
    parser.add_argument("--interval", type=int, default=POLL_SECONDS, help="Job polling interval in seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s nexcy...%(message)s".replace("nexcy...", "nexcyr.agent "),
    )
    agent = NexCYRAgent(args.server, args.token, args.interval)

    try:
        agent.run()
    except KeyboardInterrupt:
        LOG.info("Agent stopped by operator.")
        return 0
    except requests.RequestException as exc:
        LOG.error("Cloud connection failed: %s", exc)
        return 2
    except Exception as exc:
        LOG.error("Agent stopped: %s", exc)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
