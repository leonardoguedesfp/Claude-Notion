"""BUG-N3: Integration test for /data_sources/{id}/query endpoint.

Skipped in CI unless NOTION_TEST_TOKEN env var is set.
Run manually: NOTION_TEST_TOKEN=secret_... pytest tests/test_endpoint_data_source.py -v
"""
import os

import pytest


@pytest.mark.skipif(
    not os.getenv("NOTION_TEST_TOKEN"),
    reason="requires NOTION_TEST_TOKEN env var (real Notion token)",
)
def test_query_data_source_processos():
    """Confirms DATA_SOURCES IDs are valid data_source_ids for the query endpoint."""
    from notion_bulk_edit.notion_api import NotionClient
    from notion_bulk_edit.config import DATA_SOURCES

    client = NotionClient(os.getenv("NOTION_TEST_TOKEN"))
    pages = list(client.query_all(DATA_SOURCES["Processos"]))
    assert len(pages) > 0, "Expected at least one page in Processos"


@pytest.mark.skipif(
    not os.getenv("NOTION_TEST_TOKEN"),
    reason="requires NOTION_TEST_TOKEN env var (real Notion token)",
)
def test_query_data_source_clientes():
    from notion_bulk_edit.notion_api import NotionClient
    from notion_bulk_edit.config import DATA_SOURCES

    client = NotionClient(os.getenv("NOTION_TEST_TOKEN"))
    pages = list(client.query_all(DATA_SOURCES["Clientes"]))
    assert len(pages) > 0, "Expected at least one page in Clientes"
