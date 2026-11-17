"""Local regression tests for literature screening and full-text storage."""

from pathlib import Path

import pytest

from csdis.database import connect
from csdis.literature import _save_search, review_literature_record, store_full_text


@pytest.fixture
def literature_db(tmp_path: Path):
    connection = connect(tmp_path / "literature.sqlite3")
    result = _save_search(
        connection,
        "Crossref",
        "construction safety",
        10,
        {"page": 1},
        [{"title": "Safety monitoring on construction sites", "doi": "10.1234/example", "year": 2024}],
    )
    record_id = connection.execute(
        "SELECT record_id FROM literature_records WHERE query_id=?", (result["query_id"],)
    ).fetchone()[0]
    yield connection, record_id, tmp_path / "full_text"
    connection.close()


def test_full_text_upload_is_hashed_deduplicated_and_review_guarded(literature_db):
    connection, record_id, storage_root = literature_db
    content = b"Example local full-text PDF bytes"

    attachment, created = store_full_text(
        connection, storage_root, record_id, "../../paper.pdf", content, "application/pdf"
    )
    duplicate, duplicate_created = store_full_text(
        connection, storage_root, record_id, "paper-copy.pdf", content, "application/pdf"
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate["file_id"] == attachment["file_id"]
    assert attachment["sha256"]
    assert attachment["file_size"] == len(content)
    stored_path = (storage_root / attachment["storage_path"]).resolve()
    assert stored_path.is_relative_to(storage_root.resolve())
    assert stored_path.read_bytes() == content
    assert connection.execute("SELECT COUNT(*) FROM literature_full_texts").fetchone()[0] == 1

    review_literature_record(
        connection, record_id, "Include", "User upload", "AB", "Reviewed attached full text."
    )
    saved = connection.execute(
        "SELECT screening_status, full_text_status, reviewer FROM literature_records WHERE record_id=?",
        (record_id,),
    ).fetchone()
    assert tuple(saved) == ("Include", "User upload", "AB")


def test_user_upload_status_requires_an_attached_file(literature_db):
    connection, record_id, _ = literature_db
    with pytest.raises(ValueError, match="Attach a full-text file"):
        review_literature_record(
            connection, record_id, "Maybe", "User upload", "AB", "Needs full-text review."
        )


def _capture_params(monkeypatch, payload):
    import httpx
    import csdis.literature as literature

    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"], captured["params"] = url, dict(params)
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(literature.httpx, "get", fake_get)
    return captured


def test_openalex_title_abstract_and_year_filters_are_sent_and_logged(tmp_path: Path, monkeypatch):
    from csdis.literature import search_openalex

    captured = _capture_params(monkeypatch, {"meta": {"count": 0}, "results": []})
    connection = connect(tmp_path / "lit.sqlite3")
    search_openalex(connection, '"construction safety" AND "hand tool"', 10, 1, field="title_and_abstract", from_year=2015)
    assert "search" not in captured["params"]
    assert captured["params"]["filter"] == ('title_and_abstract.search:"construction safety" AND "hand tool",'
                                            "from_publication_date:2015-01-01")
    logged = connection.execute("SELECT filters_json FROM literature_searches").fetchone()[0]
    assert "from_publication_date:2015-01-01" in logged
    with pytest.raises(ValueError):
        search_openalex(connection, "a, b", field="title_and_abstract")
    connection.close()


def test_crossref_from_year_filter(tmp_path: Path, monkeypatch):
    from csdis.literature import search_crossref

    captured = _capture_params(monkeypatch, {"message": {"total-results": 0, "items": []}})
    connection = connect(tmp_path / "lit.sqlite3")
    search_crossref(connection, "construction safety hand tool", 10, 1, from_year=2015)
    assert captured["params"]["filter"] == "from-pub-date:2015-01-01"
    assert captured["params"]["query.bibliographic"] == "construction safety hand tool"
    connection.close()
