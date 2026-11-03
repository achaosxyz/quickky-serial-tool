"""Local environment loading and preflight checks for serial E2E tests."""

from pathlib import Path

import serial.tools.list_ports


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / "dev.env"
TX_PORT_KEY = "QSERIAL_E2E_TX_PORT"
RX_PORT_KEY = "QSERIAL_E2E_RX_PORT"


def load_endpoints(path=DEFAULT_ENV_FILE):
    """Return the configured TX/RX endpoints from a local environment file."""
    env_path = Path(path)
    if not env_path.is_file():
        raise RuntimeError(
            f"E2E environment file not found: {env_path}; copy dev.env.template first"
        )

    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()

    try:
        endpoints = (values[TX_PORT_KEY], values[RX_PORT_KEY])
    except KeyError as error:
        raise RuntimeError(f"Missing E2E endpoint setting: {error.args[0]}") from error
    if not all(endpoints):
        raise RuntimeError("E2E serial endpoints must be non-empty")
    return endpoints


def ensure_ports_available(endpoints):
    """Fail before GUI testing when either configured serial endpoint is absent."""
    available = {port.device for port in serial.tools.list_ports.comports()}
    missing = [port for port in endpoints if port not in available]
    if missing:
        raise RuntimeError(f"E2E serial endpoints are unavailable: {', '.join(missing)}")
