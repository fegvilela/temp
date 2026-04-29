"""
Notion database read/write client.

NOTE: This file is named notion_client.py, which shadows the `notion-client`
PyPI package (imported as `from notion_client import Client`).  To avoid that
circular naming conflict we call the Notion REST API directly through
`requests` — the behaviour is identical to using the SDK wrapper.

Database property schema expected on the Notion side:
    Name        — title
    Type        — select  ("Photo" | "Link")
    Sender      — rich_text
    Date        — date
    Category    — select  (e.g. "Kitchen", "Living Room", …)
    URL         — url     (links only; leave blank for photos)
    Filename    — rich_text (photos only; leave blank for links)
    Hash        — rich_text (SHA-256 of the photo file; used for dedup)
    Thumbnail   — files   (og:image URL for links; leave blank for photos)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import requests

from parser import ChatItem  # noqa: F401 — used for type hints only


_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_PAGE_SIZE = 100  # Notion maximum per query request


class NotionClient:
    """Thin client for reading and writing to a single Notion database."""

    def __init__(self, api_key: str, database_id: str) -> None:
        self._db_id = database_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": _NOTION_VERSION,
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._session.post(f"{_API_BASE}{path}", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _rich_text(value: str) -> list[dict]:
        """Build a Notion rich_text array from a plain string."""
        return [{"type": "text", "text": {"content": value[:2000]}}]

    # ------------------------------------------------------------------
    # Deduplication support
    # ------------------------------------------------------------------

    def get_existing_entries(self) -> dict[str, set]:
        """
        Fetch all pages in the database and return the known URLs and hashes.

        Returns:
            {
                "urls":   set of URL strings already stored,
                "hashes": set of photo SHA-256 hashes already stored,
            }
        """
        urls: set[str] = set()
        hashes: set[str] = set()
        cursor: Optional[str] = None

        while True:
            payload: dict = {"page_size": _PAGE_SIZE}
            if cursor:
                payload["start_cursor"] = cursor

            data = self._post(f"/databases/{self._db_id}/query", payload)

            for page in data.get("results", []):
                props = page.get("properties", {})

                # Extract URL property
                url_prop = props.get("URL", {})
                url_val = url_prop.get("url")
                if url_val:
                    urls.add(url_val)

                # Extract Hash property (rich_text)
                hash_prop = props.get("Hash", {})
                hash_blocks = hash_prop.get("rich_text", [])
                if hash_blocks:
                    hash_val = hash_blocks[0].get("text", {}).get("content", "").strip()
                    if hash_val:
                        hashes.add(hash_val)

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return {"urls": urls, "hashes": hashes}

    # ------------------------------------------------------------------
    # Writing new entries
    # ------------------------------------------------------------------

    def add_photo(self, item: "ChatItem", category: str) -> str:
        """
        Create a Notion page for a WhatsApp photo.

        Returns the new page ID.
        """
        import os

        filename = os.path.basename(item.content)
        properties = {
            "Name": {
                "title": self._rich_text(filename)
            },
            "Type": {
                "select": {"name": "Photo"}
            },
            "Sender": {
                "rich_text": self._rich_text(item.sender)
            },
            "Date": {
                "date": {"start": item.date.strftime("%Y-%m-%d")}
            },
            "Category": {
                "select": {"name": category}
            },
            "Filename": {
                "rich_text": self._rich_text(filename)
            },
            "Hash": {
                "rich_text": self._rich_text(item.file_hash or "")
            },
        }

        payload = {
            "parent": {"database_id": self._db_id},
            "properties": properties,
        }
        page = self._post("/pages", payload)
        return page["id"]

    def add_link(
        self,
        item: "ChatItem",
        category: str,
        metadata: dict,
    ) -> str:
        """
        Create a Notion page for a WhatsApp link.

        Args:
            item:     The ChatItem with type="link".
            category: Gemini-assigned category string.
            metadata: Dict with keys "title" (str) and "og_image" (str | None).

        Returns the new page ID.
        """
        title = (metadata.get("title") or item.content)[:500]
        og_image = metadata.get("og_image")

        properties: dict = {
            "Name": {
                "title": self._rich_text(title)
            },
            "Type": {
                "select": {"name": "Link"}
            },
            "Sender": {
                "rich_text": self._rich_text(item.sender)
            },
            "Date": {
                "date": {"start": item.date.strftime("%Y-%m-%d")}
            },
            "Category": {
                "select": {"name": category}
            },
            "URL": {
                "url": item.content
            },
        }

        if og_image:
            properties["Thumbnail"] = {
                "files": [
                    {
                        "name": "thumbnail",
                        "type": "external",
                        "external": {"url": og_image},
                    }
                ]
            }

        payload = {
            "parent": {"database_id": self._db_id},
            "properties": properties,
        }
        page = self._post("/pages", payload)
        return page["id"]
