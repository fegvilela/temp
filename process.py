"""
WhatsApp → Notion processor  (CLI entrypoint).

Usage:
    python process.py --zip ~/Downloads/chat.zip

Required environment variables (via .env or shell):
    GEMINI_API_KEY      — Google AI Studio API key
    NOTION_API_KEY      — Notion integration token (starts with "secret_")
    NOTION_DATABASE_ID  — ID of the target Notion database

The tool:
  1. Extracts all photos and links from the WhatsApp zip export.
  2. Deduplicates against existing Notion entries (URL for links, SHA-256 for photos).
  3. Categorises each new item with Gemini vision / text (gemini-1.5-flash).
  4. Pushes new items to Notion with metadata.
  5. Prints a summary.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from categorizer import categorize_link, categorize_photo
from dedup import is_duplicate
from notion_client import NotionClient
from parser import ChatItem, parse_chat_zip


# ---------------------------------------------------------------------------
# Link metadata fetching
# ---------------------------------------------------------------------------

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WhatsAppNotionBot/1.0; "
        "+https://github.com/you/whatsapp-refs)"
    )
}
_FETCH_TIMEOUT = 12  # seconds


def fetch_link_metadata(url: str) -> dict:
    """
    Fetch a URL and extract its title and og:image.

    Returns:
        {
            "title":    str  — page title (falls back to the URL itself),
            "og_image": str | None — absolute og:image URL if present,
            "description": str — og:description or meta description,
        }
    Silently degrades on network or parsing errors.
    """
    try:
        resp = requests.get(
            url, headers=_FETCH_HEADERS, timeout=_FETCH_TIMEOUT, allow_redirects=True
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Title: prefer og:title, then <title>
        og_title_tag = soup.find("meta", property="og:title")
        title: str = (
            og_title_tag["content"].strip()
            if og_title_tag and og_title_tag.get("content")
            else ""
        )
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""
        title = title or url

        # og:image
        og_img_tag = soup.find("meta", property="og:image")
        og_image: str | None = (
            og_img_tag["content"].strip()
            if og_img_tag and og_img_tag.get("content")
            else None
        )

        # Description: prefer og:description, then meta description
        og_desc_tag = soup.find("meta", property="og:description")
        description: str = (
            og_desc_tag["content"].strip()
            if og_desc_tag and og_desc_tag.get("content")
            else ""
        )
        if not description:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            description = (
                meta_desc["content"].strip()
                if meta_desc and meta_desc.get("content")
                else ""
            )

        return {"title": title, "og_image": og_image, "description": description}

    except Exception as exc:
        print(f"    [warn] Could not fetch metadata for {url}: {exc}")
        return {"title": url, "og_image": None, "description": ""}


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process.py",
        description=(
            "Extract photos and links from a WhatsApp chat zip, categorise "
            "them with Gemini AI, and push new items to a Notion database."
        ),
    )
    parser.add_argument(
        "--zip",
        required=True,
        metavar="PATH",
        help="Path to the WhatsApp chat export .zip file.",
    )
    return parser


# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load required env vars from .env (if present) and validate them."""
    load_dotenv()

    keys = {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
        "NOTION_API_KEY": os.getenv("NOTION_API_KEY", ""),
        "NOTION_DATABASE_ID": os.getenv("NOTION_DATABASE_ID", ""),
    }
    missing = [k for k, v in keys.items() if not v]
    if missing:
        print(
            "Error: The following required environment variables are not set:\n"
            + "\n".join(f"  {k}" for k in missing)
            + "\n\nCopy .env.example to .env and fill in your credentials."
        )
        sys.exit(1)

    return keys


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    args = build_arg_parser().parse_args()
    env = load_env()

    zip_path = str(Path(args.zip).expanduser().resolve())
    if not Path(zip_path).is_file():
        print(f"Error: File not found: {zip_path}")
        sys.exit(1)

    # ── Step 1: parse zip ─────────────────────────────────────────────────
    print(f"Parsing {zip_path} …")
    try:
        items, temp_dir = parse_chat_zip(zip_path)
    except Exception as exc:
        print(f"Error: Could not parse zip file: {exc}")
        sys.exit(1)

    photos = [i for i in items if i.type == "photo"]
    links = [i for i in items if i.type == "link"]
    print(f"  Found {len(photos)} photo(s) and {len(links)} link(s) in the export.")

    # ── Step 2: fetch existing Notion entries for deduplication ───────────
    notion = NotionClient(env["NOTION_API_KEY"], env["NOTION_DATABASE_ID"])
    print("Fetching existing Notion entries for deduplication …")
    try:
        existing = notion.get_existing_entries()
    except Exception as exc:
        print(f"Error: Could not query Notion database: {exc}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(1)

    print(
        f"  Notion has {len(existing['urls'])} existing link(s) "
        f"and {len(existing['hashes'])} existing photo(s)."
    )

    # ── Step 3: process each item ─────────────────────────────────────────
    added = 0
    skipped = 0
    errors = 0

    for idx, item in enumerate(items, start=1):
        tag = f"[{idx}/{len(items)}]"

        if is_duplicate(item, existing):
            print(f"  {tag} Skipping duplicate {item.type}: {item.content[:80]}")
            skipped += 1
            continue

        print(f"  {tag} Processing {item.type} from {item.sender} ({item.date.date()}) …")

        try:
            if item.type == "photo":
                category = categorize_photo(item.content, env["GEMINI_API_KEY"])
                print(f"        Category: {category}")
                notion.add_photo(item, category)
                # Update local dedup set so duplicates within this run are caught
                if item.file_hash:
                    existing["hashes"].add(item.file_hash)

            elif item.type == "link":
                metadata = fetch_link_metadata(item.content)
                category = categorize_link(
                    item.content,
                    metadata.get("title", ""),
                    metadata.get("description", ""),
                    env["GEMINI_API_KEY"],
                )
                print(f"        Title:    {metadata['title'][:60]}")
                print(f"        Category: {category}")
                notion.add_link(item, category, metadata)
                existing["urls"].add(item.content)

            added += 1

        except Exception as exc:
            print(f"        [error] Could not process item: {exc}")
            errors += 1

    # ── Step 4: cleanup and summary ───────────────────────────────────────
    shutil.rmtree(temp_dir, ignore_errors=True)

    print()
    print("─" * 50)
    print(f"  {added} new item(s) added to Notion")
    print(f"  {skipped} duplicate(s) skipped")
    if errors:
        print(f"  {errors} item(s) failed (see warnings above)")
    print("─" * 50)


if __name__ == "__main__":
    main()
