import re


def parse_nmap_output(output: str):
    """
    Parse basic Nmap output into structured port/service findings.
    """

    findings = []

    if not output:
        return findings

    # Match lines like:
    # 53/tcp  open  tcpwrapped
    # 443/tcp open  ssl/https?
    pattern = re.compile(
        r"^(\d+)/(\w+)\s+(\w+)\s+(\S+)(?:\s+(.*))?$"
    )

    for line in output.splitlines():
        line = line.strip()

        match = pattern.match(line)

        if not match:
            continue

        port = int(match.group(1))
        protocol = match.group(2)
        state = match.group(3)
        service = match.group(4)
        version = (match.group(5) or "").strip()

        # Basic risk classification
        if state == "open":
            if port in [21, 23, 445, 3389]:
                risk = "high"
            elif port in [22, 25, 53, 80, 110, 139, 443]:
                risk = "medium"
            else:
                risk = "low"
        else:
            risk = "info"

        findings.append({
            "port": port,
            "protocol": protocol,
            "state": state,
            "service": service,
            "version": version,
            "risk": risk
        })

    return findings