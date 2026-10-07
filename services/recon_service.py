"""Safe, authorized reconnaissance primitives.

All functions require an already-validated target value; the routes layer
enforces that the target record is authorized before anything runs here.
No destructive techniques are used: DNS lookups, TCP connect port checks
and nmap service enumeration only.
"""

import ipaddress
import json
import logging
import socket

from services.nmap_parser import parse_nmap_output
from services.nmap_service import is_safe_scan_value, nmap_available, run_nmap

logger = logging.getLogger("nexcyr.recon")

COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
    993, 995, 1433, 3306, 3389, 5432, 5900, 8080, 8443,
]

CONNECT_TIMEOUT = 1.5


def resolve_host(value: str) -> dict:
    """Host discovery via DNS resolution (no packets crafted)."""
    result = {
        "value": value,
        "resolved_ips": [],
        "reverse_dns": [],
        "is_ip": False,
        "status": "completed",
    }

    try:
        ipaddress.ip_address(value)
        result["is_ip"] = True
        result["resolved_ips"] = [value]
    except ValueError:
        try:
            infos = socket.getaddrinfo(value, None)
            result["resolved_ips"] = sorted({info[4][0] for info in infos})
        except socket.gaierror:
            result["status"] = "unresolved"
            return result

    for ip in result["resolved_ips"][:3]:
        try:
            result["reverse_dns"].append(socket.gethostbyaddr(ip)[0])
        except (socket.herror, socket.gaierror, OSError):
            pass

    return result


def check_ports(value: str, ports=None) -> dict:
    """Port discovery using plain TCP connect checks."""
    ports = ports or COMMON_PORTS
    open_ports = []

    try:
        host = value
        if not _is_ip(value):
            host = socket.gethostbyname(value)
    except (socket.gaierror, OSError):
        return {
            "value": value,
            "status": "unreachable",
            "open_ports": [],
            "checked_ports": ports,
        }

    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        try:
            if sock.connect_ex((host, port)) == 0:
                open_ports.append(port)
        except OSError:
            pass
        finally:
            sock.close()

    return {
        "value": value,
        "status": "completed",
        "open_ports": open_ports,
        "checked_ports": ports,
    }


def enumerate_services(value: str) -> dict:
    """Service enumeration via nmap -sV when available."""
    if not nmap_available():
        return {
            "value": value,
            "status": "nmap_unavailable",
            "services": [],
            "error": (
                "Nmap is not installed; service enumeration skipped. "
                "No results were fabricated."
            ),
        }

    scan = run_nmap(value, service_version=True)
    if scan["status"] != "completed":
        return {
            "value": value,
            "status": scan["status"],
            "services": [],
            "error": scan.get("error") or "Nmap scan did not complete.",
        }

    return {
        "value": value,
        "status": "completed",
        "services": parse_nmap_output(scan["output"]),
    }


def run_recon(value: str, recon_type: str) -> dict:
    """Dispatch one authorized recon operation and return serializable data."""
    if not is_safe_scan_value(value):
        raise ValueError(
            "Target value is not a valid IP, hostname, domain or small network."
        )

    if recon_type == "host_discovery":
        data = resolve_host(value)
    elif recon_type == "port_discovery":
        data = check_ports(value)
    elif recon_type == "service_enumeration":
        data = enumerate_services(value)
    else:
        raise ValueError(
            "recon_type must be host_discovery, port_discovery "
            "or service_enumeration."
        )

    logger.info("Recon %s on %s -> %s", recon_type, value, data.get("status"))
    return data


def dump_result(data: dict) -> str:
    return json.dumps(data, default=str)


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
