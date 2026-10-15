from somnia.ingest.chunking import chunk_text
from somnia.ingest.redaction import redact_secrets


def test_redacts_common_secret_shapes() -> None:
    text = (
        "export OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\n"
        "aws AKIAABCDEFGHIJKLMNOP and ghp_" + "a" * 36 + "\n"
        "url postgres://app:hunter2secret@db.local/x\n"
        "password = 'correcthorse'\n"
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
    )
    result = redact_secrets(text)
    for secret in (
        "sk-abcdef",
        "AKIAABCDEF",
        "ghp_aaaa",
        "hunter2secret",
        "correcthorse",
        "abcdefghijklmnopqrstuvwxyz\n",
    ):
        assert secret not in result.text
    assert result.count >= 6
    assert "postgres://app:[REDACTED]@db.local/x" in result.text


def test_leaves_plain_text_alone() -> None:
    result = redact_secrets("run uv run pytest and check the token budget logic")
    assert result.count == 0


def test_chunking_overlaps_and_covers_text() -> None:
    text = "\n".join(f"line {i} " + "x" * 40 for i in range(100))
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    assert chunks[0].startswith("line 0")
    assert chunks[-1].endswith("x" * 40)
    assert chunk_text("   ", 500, 50) == []
