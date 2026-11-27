import json
from collections.abc import Iterator

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from somnia.config import ProviderSettings
from somnia.memory.inference import SymphonyLlm


def _stream(*deltas: dict[str, object]) -> httpx.Response:
    def encode() -> Iterator[str]:
        for delta in deltas:
            yield "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\n"
        yield "data: [DONE]\n\n"

    return httpx.Response(
        200, content="".join(encode()), headers={"content-type": "text/event-stream"}
    )


def _settings() -> ProviderSettings:
    return ProviderSettings(llm_base_url="https://model.example/v1", llm_api_key=SecretStr("test"))


def test_streaming_inference_validates_the_session_digest() -> None:
    calls = 0

    def model(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["messages"][1]["content"] == "event data"
        assert "tools" not in body
        if calls == 1:
            return _stream({"content": '{"goal":"refactor",'}, {"content": '"state":"working"}'})
        return _stream({"content": '{"goal":"missing state"}'})

    with SymphonyLlm(_settings(), transport=httpx.MockTransport(model)) as llm:
        assert llm.summarize_session("event data").state == "working"
        with pytest.raises(ValidationError):
            llm.summarize_session("event data")


def test_harness_reads_evidence_before_resolving_an_ambiguous_conflict() -> None:
    def model(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["name"] == "read_evidence"
        if any(message["role"] == "tool" for message in body["messages"]):
            assert any("new config" in str(message["content"]) for message in body["messages"])
            return _stream({"content": '{"action":"supersede","content":"Use the new config"}'})
        return _stream(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "type": "function",
                        "id": "call_evidence",
                        "function": {"name": "read_evidence", "arguments": "{}"},
                    }
                ]
            }
        )

    with SymphonyLlm(_settings(), transport=httpx.MockTransport(model)) as llm:
        result = llm.investigate_conflict(
            "Use old config", "Use new config", "repo", lambda: "new config"
        )
        assert result is not None
        assert result.action == "supersede"
