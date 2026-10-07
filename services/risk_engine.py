"""
NexCYR Risk Engine

Responsible for:
- Finding-level risk scoring
- Service/port risk analysis
- Exposure analysis
- Risk factor generation
- Security recommendations
- Overall scan risk calculation
- Risk summaries
"""

from typing import Any, Dict, List


# ============================================================
# BASE SEVERITY SCORES
# ============================================================

SEVERITY_SCORES = {
    "critical": 90,
    "high": 75,
    "medium": 50,
    "low": 25,
    "informational": 5,
    "info": 5
}


# ============================================================
# RISKY PORT DATABASE
# ============================================================

HIGH_RISK_PORTS = {
    21: "FTP",
    23: "Telnet",
    445: "SMB",
    3389: "RDP"
}


MEDIUM_RISK_PORTS = {
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    139: "NetBIOS",
    443: "HTTPS"
}


# ============================================================
# SENSITIVE SERVICES
# ============================================================

SENSITIVE_SERVICES = {
    "ftp",
    "telnet",
    "smb",
    "microsoft-ds",
    "rdp",
    "ms-wbt-server",
    "netbios",
    "vnc",
    "redis",
    "mongodb",
    "mysql",
    "postgresql",
    "postgres",
    "mssql",
    "oracle"
}


# ============================================================
# INSECURE / LEGACY SERVICES
# ============================================================

INSECURE_SERVICES = {
    "ftp",
    "telnet",
    "pop3",
    "imap",
    "http"
}


# ============================================================
# ENCRYPTED SERVICES
# ============================================================

ENCRYPTED_SERVICES = {
    "https",
    "ssh",
    "ssl",
    "tls"
}


# ============================================================
# COMMON MANAGEMENT PORTS
# ============================================================

MANAGEMENT_PORTS = {
    22: "SSH",
    23: "Telnet",
    3389: "RDP",
    5900: "VNC",
    5901: "VNC"
}


# ============================================================
# DATABASE PORTS
# ============================================================

DATABASE_PORTS = {
    1433: "MSSQL",
    1521: "Oracle",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    27017: "MongoDB"
}


# ============================================================
# WEB PORTS
# ============================================================

WEB_PORTS = {
    80: "HTTP",
    443: "HTTPS",
    8080: "HTTP",
    8000: "HTTP",
    8443: "HTTPS"
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_text(value: Any) -> str:
    """
    Safely convert any value into lowercase text.
    """

    if value is None:
        return ""

    return str(value).strip().lower()


def get_base_score(severity: str) -> int:
    """
    Get base score from severity.
    """

    return SEVERITY_SCORES.get(
        normalize_text(severity),
        SEVERITY_SCORES["informational"]
    )


def classify_risk(score: int) -> str:
    """
    Convert numerical score into risk level.
    """

    if score >= 90:
        return "critical"

    if score >= 70:
        return "high"

    if score >= 40:
        return "medium"

    if score >= 15:
        return "low"

    return "informational"


# ============================================================
# RECOMMENDATION ENGINE
# ============================================================

def get_recommendations(
    port: Any,
    service: str,
    risk_level: str
) -> List[str]:

    recommendations = []

    service = normalize_text(service)

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = None

    # FTP
    if port == 21 or service == "ftp":
        recommendations.append(
            "Disable FTP if it is not required."
        )
        recommendations.append(
            "Prefer SFTP or another encrypted file-transfer protocol."
        )

    # Telnet
    if port == 23 or service == "telnet":
        recommendations.append(
            "Disable Telnet and replace it with SSH."
        )

    # SMB
    if port == 445 or service in {"smb", "microsoft-ds"}:
        recommendations.append(
            "Restrict SMB access to trusted hosts and networks."
        )
        recommendations.append(
            "Review SMB configuration and disable unnecessary SMB exposure."
        )

    # RDP
    if port == 3389 or service in {"rdp", "ms-wbt-server"}:
        recommendations.append(
            "Restrict RDP access using firewall rules or VPN."
        )
        recommendations.append(
            "Enable strong authentication and account lockout controls."
        )

    # HTTP
    if port == 80 or service == "http":
        recommendations.append(
            "Use HTTPS/TLS for sensitive web traffic."
        )

    # Database
    if port in DATABASE_PORTS:
        recommendations.append(
            "Restrict database access to trusted application hosts."
        )
        recommendations.append(
            "Do not expose database services directly to untrusted networks."
        )

    # Generic high/critical
    if risk_level in {"critical", "high"}:
        recommendations.append(
            "Prioritize investigation and remediation of this finding."
        )

    # Generic medium
    elif risk_level == "medium":
        recommendations.append(
            "Review the service configuration and network exposure."
        )

    # Remove duplicates while preserving order
    return list(dict.fromkeys(recommendations))


# ============================================================
# SINGLE FINDING RISK ENGINE
# ============================================================

def calculate_finding_risk(finding: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate a detailed risk assessment for one finding.

    Returns:
        risk_score
        risk_level
        factors
        recommendations
        confidence
    """

    severity = normalize_text(
        finding.get("severity", "informational")
    )

    port = finding.get("port")

    service = normalize_text(
        finding.get("service", "")
    )

    version = normalize_text(
        finding.get("version", "")
    )

    state = normalize_text(
        finding.get("state", "")
    )

    # --------------------------------------------------------
    # BASE SCORE
    # --------------------------------------------------------

    base_score = get_base_score(severity)

    score = base_score

    factors = []

    # --------------------------------------------------------
    # PORT NORMALIZATION
    # --------------------------------------------------------

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = None

    # --------------------------------------------------------
    # HIGH-RISK PORT
    # --------------------------------------------------------

    if port in HIGH_RISK_PORTS:

        score += 15

        factors.append(
            f"Potentially risky service exposed on port {port}"
        )

    # --------------------------------------------------------
    # MEDIUM-RISK PORT
    # --------------------------------------------------------

    elif port in MEDIUM_RISK_PORTS:

        score += 5

        factors.append(
            f"Network service detected on port {port}"
        )

    # --------------------------------------------------------
    # OPEN PORT
    # --------------------------------------------------------

    if state == "open":

        score += 5

        factors.append(
            "Port is open on the scanned host"
        )

    # --------------------------------------------------------
    # SENSITIVE SERVICE
    # --------------------------------------------------------

    if service in SENSITIVE_SERVICES:

        score += 10

        factors.append(
            f"Sensitive service detected: {service}"
        )

    # --------------------------------------------------------
    # INSECURE / LEGACY SERVICE
    # --------------------------------------------------------

    if service in INSECURE_SERVICES:

        score += 10

        factors.append(
            f"Potentially insecure or legacy protocol: {service}"
        )

    # --------------------------------------------------------
    # MANAGEMENT SERVICE
    # --------------------------------------------------------

    if port in MANAGEMENT_PORTS:

        score += 5

        factors.append(
            f"Remote management service detected on port {port}"
        )

    # --------------------------------------------------------
    # DATABASE SERVICE
    # --------------------------------------------------------

    if port in DATABASE_PORTS:

        score += 10

        factors.append(
            f"Database service detected on port {port}"
        )

    # --------------------------------------------------------
    # WEB SERVICE
    # --------------------------------------------------------

    if port in WEB_PORTS:

        factors.append(
            f"Web service detected on port {port}"
        )

    # --------------------------------------------------------
    # HTTP WITHOUT ENCRYPTION
    # --------------------------------------------------------

    if port == 80 or service == "http":

        score += 5

        factors.append(
            "HTTP traffic may be unencrypted"
        )

    # --------------------------------------------------------
    # VERSION INFORMATION
    # --------------------------------------------------------

    if version:

        factors.append(
            f"Service version identified: {version}"
        )

    # --------------------------------------------------------
    # UNKNOWN SERVICE
    # --------------------------------------------------------

    if not service:

        factors.append(
            "Service identification is incomplete"
        )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    final_score = min(max(score, 0), 100)

    # --------------------------------------------------------
    # RISK LEVEL
    # --------------------------------------------------------

    risk_level = classify_risk(final_score)

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    confidence = "medium"

    if service and state:
        confidence = "high"

    if not service or not state:
        confidence = "low"

    # --------------------------------------------------------
    # RECOMMENDATIONS
    # --------------------------------------------------------

    recommendations = get_recommendations(
        port,
        service,
        risk_level
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {
        "risk_score": final_score,
        "risk_level": risk_level,
        "risk_factors": factors,
        "recommendations": recommendations,
        "confidence": confidence
    }


# ============================================================
# OVERALL RISK ENGINE
# ============================================================

def calculate_overall_risk(
    findings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate overall risk for a complete scan.

    The highest individual risk is used as the primary
    overall security risk so the overall score never
    understates a critical finding.
    """

    # --------------------------------------------------------
    # EMPTY SCAN
    # --------------------------------------------------------

    if not findings:

        return {
            "overall_score": 0,
            "overall_risk": "informational",
            "total_findings": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "informational": 0,
            "risk_distribution": {},
            "highest_risk_score": 0,
            "highest_risk_level": "informational",
            "highest_risk_finding": None,
            "findings": []
        }

    # --------------------------------------------------------
    # ANALYZE EACH FINDING
    # --------------------------------------------------------

    analyzed_findings = []

    for finding in findings:

        result = calculate_finding_risk(finding)

        analyzed_findings.append({
            **finding,
            **result
        })

    # --------------------------------------------------------
    # COUNT RISK LEVELS
    # --------------------------------------------------------

    critical = sum(
        1
        for item in analyzed_findings
        if item["risk_level"] == "critical"
    )

    high = sum(
        1
        for item in analyzed_findings
        if item["risk_level"] == "high"
    )

    medium = sum(
        1
        for item in analyzed_findings
        if item["risk_level"] == "medium"
    )

    low = sum(
        1
        for item in analyzed_findings
        if item["risk_level"] == "low"
    )

    informational = sum(
        1
        for item in analyzed_findings
        if item["risk_level"] == "informational"
    )

    # --------------------------------------------------------
    # HIGHEST RISK FINDING
    # --------------------------------------------------------

    highest_risk_finding = max(
        analyzed_findings,
        key=lambda item: item.get("risk_score", 0)
    )

    highest_risk_score = highest_risk_finding.get(
        "risk_score",
        0
    )

    highest_risk_level = highest_risk_finding.get(
        "risk_level",
        "informational"
    )

    # --------------------------------------------------------
    # OVERALL SCORE
    # --------------------------------------------------------
    #
    # Important:
    # Overall score is based on the highest individual risk.
    #
    # This prevents a critical finding from being hidden
    # inside an average score.
    #
    # Example:
    # 95, 30, 30, 30
    #
    # Overall score = 95
    # Overall risk = critical
    #
    # --------------------------------------------------------

    overall_score = highest_risk_score

    overall_risk = classify_risk(
        overall_score
    )

    # --------------------------------------------------------
    # RISK DISTRIBUTION
    # --------------------------------------------------------

    total = len(analyzed_findings)

    risk_distribution = {
        "critical": round((critical / total) * 100, 2),
        "high": round((high / total) * 100, 2),
        "medium": round((medium / total) * 100, 2),
        "low": round((low / total) * 100, 2),
        "informational": round(
            (informational / total) * 100,
            2
        )
    }

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {
        "overall_score": overall_score,
        "overall_risk": overall_risk,

        "total_findings": total,

        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
        "informational": informational,

        "risk_distribution": risk_distribution,

        "highest_risk_score": highest_risk_score,
        "highest_risk_level": highest_risk_level,

        "highest_risk_finding": {
            "title": highest_risk_finding.get("title"),
            "port": highest_risk_finding.get("port"),
            "service": highest_risk_finding.get("service"),
            "risk_score": highest_risk_score,
            "risk_level": highest_risk_level
        },

        "findings": analyzed_findings
    }