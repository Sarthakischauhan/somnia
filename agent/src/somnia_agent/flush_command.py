"""`somnia-agent flush`: the detached uploader process. Failures are retried next flush."""

import httpx

from somnia_agent.api_client import SomniaClient, make_http
from somnia_agent.config import load_config
from somnia_agent.uploader import flush_all

FLUSH_HTTP_TIMEOUT = 10.0


def run_flush() -> int:
    config = load_config()
    if config is None:
        return 0
    try:
        with make_http(config, FLUSH_HTTP_TIMEOUT) as http:
            flush_all(SomniaClient(http))
    except httpx.HTTPError as error:
        print(f"flush incomplete, will retry on the next hook: {error}")
        return 1
    return 0
