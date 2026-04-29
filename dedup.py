"""
Deduplication logic for WhatsApp → Notion items.

Links are matched by URL; photos are matched by SHA-256 file hash.
Both lookups are O(1) against the sets returned by
NotionClient.get_existing_entries().
"""

from parser import ChatItem


def is_duplicate(item: ChatItem, existing: dict[str, set]) -> bool:
    """
    Return True if *item* is already present in the Notion database.

    Args:
        item:     A ChatItem with type "photo" or "link".
        existing: Dict with keys "urls" (set[str]) and "hashes" (set[str]),
                  as returned by NotionClient.get_existing_entries().

    Returns:
        True  → skip this item (already in Notion).
        False → process and upload this item.
    """
    if item.type == "link":
        return item.content in existing["urls"]

    if item.type == "photo":
        # file_hash is None when the file was not found in the zip (media omitted)
        if item.file_hash is None:
            return False
        return item.file_hash in existing["hashes"]

    # Unknown type — treat as non-duplicate so it surfaces for inspection
    return False
