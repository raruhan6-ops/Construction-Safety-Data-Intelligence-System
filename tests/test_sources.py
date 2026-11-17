"""Source registry, immutable uploads, and mocked retrieval tests."""

from pathlib import Path

import httpx
import pytest

from csdis.database import connect
from csdis.schemas import SourceRecord
from csdis.sources import add_source, download_source_version, store_source_version, verify_source_version
import csdis.sources as sources


@pytest.fixture
def source_workspace(tmp_path: Path):
    connection = connect(tmp_path / "sources.sqlite3")
    raw_root = tmp_path / "raw"
    record = SourceRecord(
        source_id="SRC-TEST",
        publisher="Test publisher",
        title="Test source",
        source_type="Statistics",
        canonical_url="https://public.example/data.csv",
        format="CSV",
        authority_tier="Primary",
    )
    yield connection, raw_root, record
    connection.close()


def _mock_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(sources, "_validate_public_url", lambda _url: None)
    monkeypatch.setattr(
        sources.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )


def test_source_registration_and_local_upload_are_idempotent(source_workspace):
    connection, raw_root, record = source_workspace
    assert add_source(connection, record) is True
    assert add_source(connection, record.model_copy(update={"title": "Changed title"})) is False
    assert connection.execute("SELECT title FROM sources WHERE source_id='SRC-TEST'").fetchone()[0] == "Test source"

    content = b"year,value\n2025,4.6\n"
    version_id, created, relative_path = store_source_version(
        connection, raw_root, record.source_id, "../../unsafe.csv", content
    )
    second_id, second_created, second_path = store_source_version(
        connection, raw_root, record.source_id, "renamed.csv", content
    )
    assert created is True
    assert second_created is False
    assert (second_id, second_path) == (version_id, relative_path)
    assert (raw_root / relative_path).read_bytes() == content
    assert verify_source_version(connection, raw_root, version_id)[0] is True
    assert connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 1


def test_download_saves_response_and_records_success(source_workspace, monkeypatch):
    connection, raw_root, record = source_workspace
    add_source(connection, record)
    _mock_client(
        monkeypatch,
        lambda request: httpx.Response(
            200, headers={"content-type": "text/csv"}, content=b"year,value\n2026,4.8\n"
        ),
    )

    version_id, created, path, status = download_source_version(connection, raw_root, record.source_id)
    assert created is True
    assert status == 200
    assert (raw_root / path).read_bytes() == b"year,value\n2026,4.8\n"
    attempt = connection.execute("SELECT outcome, http_status FROM source_fetch_attempts").fetchone()
    assert tuple(attempt) == ("success", 200)
    assert connection.execute("SELECT source_version_id FROM source_versions").fetchone()[0] == version_id


def test_download_follows_public_redirects(source_workspace, monkeypatch):
    connection, raw_root, record = source_workspace
    add_source(connection, record)
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        if request.url.path == "/data.csv":
            return httpx.Response(302, headers={"location": "/archive/data.csv"})
        return httpx.Response(200, headers={"content-type": "text/csv"}, content=b"ok\n")

    _mock_client(monkeypatch, handler)
    _, created, path, status = download_source_version(connection, raw_root, record.source_id)

    assert created is True
    assert status == 200
    assert requested_urls == [
        "https://public.example/data.csv", "https://public.example/archive/data.csv"
    ]
    assert (raw_root / path).read_bytes() == b"ok\n"


def test_download_rejects_redirect_to_private_address(source_workspace, monkeypatch):
    connection, raw_root, record = source_workspace
    add_source(connection, record)
    requested_urls = []
    original_validate = sources._validate_public_url

    def handler(request):
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private.csv"})

    _mock_client(monkeypatch, handler)
    monkeypatch.setattr(
        sources, "_validate_public_url",
        lambda url: original_validate(url) if "127.0.0.1" in url else None,
    )
    with pytest.raises(ValueError, match="globally routable"):
        download_source_version(connection, raw_root, record.source_id)

    assert requested_urls == ["https://public.example/data.csv"]
    assert connection.execute("SELECT outcome FROM source_fetch_attempts").fetchone()[0] == "failed"
    assert connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 0


@pytest.mark.parametrize("response_factory, max_bytes, message", [
    (lambda: httpx.Response(503, content=b"unavailable"), 100, "503"),
    (lambda: httpx.Response(200, stream=httpx.ByteStream(b"12345"), headers={"content-type": "text/plain"}), 4, "limit"),
])
def test_download_failures_are_recorded_without_storing_versions(
    source_workspace, monkeypatch, response_factory, max_bytes, message
):
    connection, raw_root, record = source_workspace
    add_source(connection, record)
    _mock_client(monkeypatch, lambda request: response_factory())

    with pytest.raises(Exception, match=message):
        download_source_version(connection, raw_root, record.source_id, max_bytes=max_bytes)

    attempt = connection.execute("SELECT outcome, error_message FROM source_fetch_attempts").fetchone()
    assert attempt["outcome"] == "failed"
    assert attempt["error_message"]
    assert connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 0


def test_private_source_urls_are_rejected_without_network_access():
    with pytest.raises(ValueError, match="globally routable"):
        sources._validate_public_url("http://127.0.0.1/private.csv")

