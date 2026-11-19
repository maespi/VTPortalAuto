"""Configuration management for VTPortal MCP server."""

import os
import sys
import logging
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Automatically load .env if present in current working directory or repository root
load_dotenv(override=True)

# Configure logging to sys.stderr so stdio stdout is never corrupted for JSON-RPC
logger = logging.getLogger("vtportal")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [vtportal] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@dataclass
class PortalConfig:
    client: str
    username: str
    password: str
    language: str = "ESP"
    headless: bool = True
    timeout_ms: int = 30000
    session_file: str = ".vtportal_session.json"

    @classmethod
    def from_env(cls) -> "PortalConfig":
        """Load configuration from environment variables."""
        client = os.getenv("VTPORTAL_CLIENT", "").strip()
        username = os.getenv("VTPORTAL_USER", "").strip()
        password = os.getenv("VTPORTAL_PASSWORD", "").strip()
        language = os.getenv("VTPORTAL_LANGUAGE", "ESP").strip() or "ESP"
        headless_str = os.getenv("HEADLESS", "true").strip().lower()
        headless = headless_str not in ("0", "false", "no")
        session_file = os.getenv("VTPORTAL_SESSION_FILE", ".vtportal_session.json").strip() or ".vtportal_session.json"
        
        try:
            timeout_ms = int(os.getenv("VTPORTAL_TIMEOUT_MS", "30000"))
        except ValueError:
            timeout_ms = 30000

        missing = []
        if not client:
            missing.append("VTPORTAL_CLIENT")
        if not username:
            missing.append("VTPORTAL_USER")
        if not password:
            missing.append("VTPORTAL_PASSWORD")

        if missing:
            raise ValueError(
                f"Missing required VTPortal credentials in environment: {', '.join(missing)}. "
                "Please configure them in your .env file or Gemini settings.json under mcpServers.vtportal.env."
            )

        return cls(
            client=client,
            username=username,
            password=password,
            language=language,
            headless=headless,
            timeout_ms=timeout_ms,
            session_file=session_file,
        )
