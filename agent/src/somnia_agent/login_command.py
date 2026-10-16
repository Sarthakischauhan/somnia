"""Store a per-device token (0600). The service has no device-code endpoint yet."""

import getpass

import httpx
from pydantic import ValidationError

from somnia_agent.api_client import SomniaClient, make_http
from somnia_agent.config import AgentConfig, save_config


def run_login(api_url: str, token: str | None, verify: bool) -> int:
    raw = token if token is not None else getpass.getpass("somnia device token (smn_...): ")
    try:
        config = AgentConfig(api_url=api_url, token=raw.strip())
    except ValidationError as error:
        print(f"login failed: {error.errors()[0]['msg']}")
        return 1
    if verify:
        try:
            with make_http(config, 5.0) as http:
                SomniaClient(http).verify()
        except httpx.HTTPError as error:
            print(f"login failed: could not verify token against {config.api_url}: {error}")
            return 1
    path = save_config(config)
    print(f"saved device token for {config.api_url} to {path} (mode 0600)")
    return 0
