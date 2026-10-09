"""Start NexCYR on Railway without relying on shell interpolation of PORT."""
import os
import sys


def main() -> None:
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        raise SystemExit(f"Invalid PORT value {raw_port!r}; expected an integer.")

    if not 1 <= port <= 65535:
        raise SystemExit(f"Invalid PORT value {port!r}; expected 1-65535.")

    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
    )


if __name__ == "__main__":
    main()
