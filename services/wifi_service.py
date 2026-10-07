import json
import platform
import re
import subprocess

VALID_SENSOR_STATUSES = {
    "available",
    "not_available",
    "error",
}

VALID_ASSESSMENT_STATUSES = {
    "created",
    "collecting",
    "completed",
    "failed",
}


def normalize_value(value, default=None):
    if value is None:
        return default

    if not isinstance(value, str):
        return value

    value = value.strip().lower()

    return value or default


def detect_wifi_interface():
    """
    Detect whether the current system exposes a Wi-Fi interface.

    This only identifies the local wireless interface.
    It does not perform any attack or disruption.
    """

    system = platform.system().lower()

    try:
        if system == "windows":

            result = subprocess.run(
                [
                    "netsh",
                    "wlan",
                    "show",
                    "interfaces",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                return {
                    "available": False,
                    "interface": None,
                    "reason": (
                        "Windows Wi-Fi interface could not be queried."
                    ),
                }

            output = result.stdout.strip()

            if not output:
                return {
                    "available": False,
                    "interface": None,
                    "reason": (
                        "No Wi-Fi interface information was returned."
                    ),
                }

            interface_name = None

            for line in output.splitlines():

                stripped = line.strip()

                if stripped.lower().startswith("name"):
                    parts = stripped.split(":", 1)

                    if len(parts) == 2:
                        interface_name = parts[1].strip()
                        break

            if interface_name:

                return {
                    "available": True,
                    "interface": interface_name,
                    "reason": "Wi-Fi interface detected.",
                }

            return {
                "available": False,
                "interface": None,
                "reason": (
                    "Wi-Fi command is available but no active "
                    "interface was detected."
                ),
            }

        if system == "linux":

            result = subprocess.run(
                [
                    "iw",
                    "dev",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                return {
                    "available": False,
                    "interface": None,
                    "reason": (
                        "Linux Wi-Fi interface could not be queried."
                    ),
                }

            output = result.stdout.strip()

            if not output:
                return {
                    "available": False,
                    "interface": None,
                    "reason": (
                        "No wireless interface was detected."
                    ),
                }

            for line in output.splitlines():

                stripped = line.strip()

                if stripped.startswith("Interface "):

                    interface_name = stripped.split(
                        " ",
                        1,
                    )[1].strip()

                    return {
                        "available": True,
                        "interface": interface_name,
                        "reason": "Wi-Fi interface detected.",
                    }

            return {
                "available": False,
                "interface": None,
                "reason": (
                    "No wireless interface was detected."
                ),
            }

        if system == "darwin":

            result = subprocess.run(
                [
                    "networksetup",
                    "-listallhardwareports",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                return {
                    "available": False,
                    "interface": None,
                    "reason": (
                        "macOS Wi-Fi interfaces could not be queried."
                    ),
                }

            lines = result.stdout.splitlines()

            for index, line in enumerate(lines):

                if "Wi-Fi" in line:

                    for next_line in lines[index + 1:index + 4]:

                        if "Device:" in next_line:

                            interface_name = (
                                next_line
                                .split(":", 1)[1]
                                .strip()
                            )

                            return {
                                "available": True,
                                "interface": interface_name,
                                "reason": (
                                    "Wi-Fi interface detected."
                                ),
                            }

            return {
                "available": False,
                "interface": None,
                "reason": (
                    "No Wi-Fi interface was detected."
                ),
            }

        return {
            "available": False,
            "interface": None,
            "reason": (
                f"Unsupported operating system: {platform.system()}"
            ),
        }

    except (
        subprocess.SubprocessError,
        OSError,
    ) as exc:

        return {
            "available": False,
            "interface": None,
            "reason": str(exc),
        }


def get_wifi_sensor_status():
    """
    Return the actual local Wi-Fi sensor/interface status.
    """

    result = detect_wifi_interface()

    if result["available"]:

        return {
            "sensor_status": "available",
            "interface": result["interface"],
            "reason": result["reason"],
        }

    return {
        "sensor_status": "not_available",
        "interface": None,
        "reason": result["reason"],
    }


def discover_windows_wifi_networks():
    """
    Discover nearby Wi-Fi networks using the Windows
    operating system's own WLAN discovery information.

    This is passive/local discovery only.

    No authentication bypass, password capture,
    deauthentication, packet injection, or disruption
    is performed.
    """

    if platform.system().lower() != "windows":
        return {
            "success": False,
            "networks": [],
            "reason": (
                "Actual Wi-Fi discovery is currently "
                "implemented for Windows."
            ),
        }

    try:

        result = subprocess.run(
            [
                "netsh",
                "wlan",
                "show",
                "networks",
                "mode=bssid",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    except (
        subprocess.SubprocessError,
        OSError,
    ) as exc:

        return {
            "success": False,
            "networks": [],
            "reason": str(exc),
        }

    if result.returncode != 0:

        error_output = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Windows Wi-Fi discovery failed."
        )

        return {
            "success": False,
            "networks": [],
            "reason": error_output,
        }

    output = result.stdout.strip()

    if not output:

        return {
            "success": True,
            "networks": [],
            "reason": (
                "Windows returned no nearby Wi-Fi networks."
            ),
        }

    networks = []

    current_network = None
    current_bssid = None

    current_language = "english"

    for raw_line in output.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        lower_line = line.lower()

        # Detect SSID lines.
        if re.match(
            r"^SSID\s+\d+\s*:",
            line,
            re.IGNORECASE,
        ):

            if current_bssid is not None and current_network is not None:
                current_network["bssid"] = current_bssid
                networks.append(current_network)

            current_bssid = None

            parts = line.split(":", 1)

            ssid = (
                parts[1].strip()
                if len(parts) == 2
                else ""
            )

            current_network = {
                "ssid": ssid,
                "bssid": None,
                "signal": None,
                "radio_type": None,
                "authentication": None,
                "cipher": None,
                "channel": None,
            }

            current_language = "english"
            continue

        if current_network is None:
            continue

        # Detect BSSID lines.
        if lower_line.startswith("bssid"):

            parts = line.split(":", 1)

            if len(parts) == 2:

                current_bssid = parts[1].strip()

                if (
                    current_network.get("bssid")
                    and current_bssid != current_network["bssid"]
                ):

                    networks.append(current_network)

                    current_network = {
                        "ssid": current_network.get("ssid"),
                        "bssid": current_bssid,
                        "signal": None,
                        "radio_type": None,
                        "authentication": None,
                        "cipher": None,
                        "channel": None,
                    }

                else:
                    current_network["bssid"] = current_bssid

            continue

        # Signal
        if lower_line.startswith("signal"):

            parts = line.split(":", 1)

            if len(parts) == 2:
                current_network["signal"] = parts[1].strip()

            continue

        # Radio type
        if lower_line.startswith("radio type"):

            parts = line.split(":", 1)

            if len(parts) == 2:
                current_network["radio_type"] = parts[1].strip()

            continue

        # Authentication
        if lower_line.startswith("authentication"):

            parts = line.split(":", 1)

            if len(parts) == 2:
                current_network["authentication"] = (
                    parts[1].strip()
                )

            continue

        # Cipher
        if lower_line.startswith("cipher"):

            parts = line.split(":", 1)

            if len(parts) == 2:
                current_network["cipher"] = parts[1].strip()

            continue

        # Channel
        if lower_line.startswith("channel"):

            parts = line.split(":", 1)

            if len(parts) == 2:
                current_network["channel"] = parts[1].strip()

            continue

    # Save the final discovered BSSID/network.
    if current_network is not None:

        if current_bssid is not None:
            current_network["bssid"] = current_bssid

        networks.append(current_network)

    # Remove incomplete entries that contain no actual BSSID.
    cleaned_networks = []

    for network in networks:

        bssid = network.get("bssid")

        if not bssid:
            continue

        cleaned_networks.append(network)

    return {
        "success": True,
        "networks": cleaned_networks,
        "reason": (
            f"Windows Wi-Fi discovery completed. "
            f"{len(cleaned_networks)} BSSID observation(s) collected."
        ),
    }


def assess_wifi_security(networks):
    """
    Generate a security summary strictly from observed
    authentication/cipher information.

    This function does not invent vulnerabilities.
    """

    if not networks:

        return {
            "risk_level": "unknown",
            "summary": (
                "No Wi-Fi observations were collected. "
                "Security posture cannot be assessed."
            ),
            "observations": [],
        }

    observations = []

    for network in networks:

        ssid = network.get("ssid")
        authentication = network.get("authentication")
        cipher = network.get("cipher")

        if authentication:
            auth_lower = authentication.lower()
        else:
            auth_lower = ""

        if cipher:
            cipher_lower = cipher.lower()
        else:
            cipher_lower = ""

        observation = {
            "ssid": ssid,
            "bssid": network.get("bssid"),
            "authentication": authentication,
            "cipher": cipher,
            "observed_security_concern": None,
        }

        # Only flag explicitly observed open networks.
        if "open" in auth_lower:

            observation["observed_security_concern"] = (
                "Open authentication observed."
            )

        # Explicitly observed WEP.
        elif "wep" in auth_lower or "wep" in cipher_lower:

            observation["observed_security_concern"] = (
                "WEP security observed."
            )

        observations.append(observation)

    concern_count = sum(
        1
        for item in observations
        if item["observed_security_concern"]
    )

    if concern_count == 0:

        return {
            "risk_level": "informational",
            "summary": (
                "Wi-Fi observations collected successfully. "
                "No explicitly weak authentication or cipher "
                "configuration was identified from the "
                "available discovery data."
            ),
            "observations": observations,
        }

    if concern_count < len(observations):

        return {
            "risk_level": "medium",
            "summary": (
                f"{concern_count} Wi-Fi observation(s) contain "
                "an explicitly observed security concern."
            ),
            "observations": observations,
        }

    return {
        "risk_level": "high",
        "summary": (
            f"{concern_count} Wi-Fi observation(s) contain "
            "an explicitly observed security concern."
        ),
        "observations": observations,
    }


