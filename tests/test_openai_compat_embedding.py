import httpx

from somnia.memory.inference import OpenAiEmbedder


def test_embedding_response_accepts_gemini_omitted_zero_index() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [2.0]}, {"embedding": [1.0]}]},
        )

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(respond))
    assert OpenAiEmbedder(client, "model").embed(["first", "second"]) == [[1.0], [2.0]]
