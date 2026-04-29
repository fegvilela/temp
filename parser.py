"""
WhatsApp chat export parser.

Handles zip extraction and message parsing from _chat.txt, supporting both
Android and iOS export formats. Extracts photo file paths and URLs.
"""

import hashlib
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}

# Matches http/https URLs, stopping at whitespace or common trailing punctuation
URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+")

# WhatsApp message line patterns (tried in order).
# Group layout for all: (date_str, time_str, sender, body)
#
# Format 1 — modern Android/iOS with square brackets:
#   [3/15/24, 9:00:00 AM] John: hello
#   [15/03/2024, 09:00:00] John: hello
#
# Format 2 — older Android without brackets:
#   3/15/24, 9:00 AM - John: hello
_BRACKETED = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*"
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)\]\s*"
    r"([^:]+):\s*(.*)$"
)
_UNBRACKETED = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s*"
    r"(\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?)\s*-\s*"
    r"([^:]+):\s*(.*)$"
)
MESSAGE_PATTERNS = [_BRACKETED, _UNBRACKETED]

# Detects media attachment lines inside message bodies.
# WhatsApp writes these when a zip is exported with media included.
_ATTACHED_SUFFIX = re.compile(
    r"^[‎‏]?(.+\.(?:jpg|jpeg|png|gif|webp|heic|heif))\s+\(file attached\)$",
    re.IGNORECASE,
)
_ATTACHED_BRACKET = re.compile(
    r"^<attached:\s*(.+\.(?:jpg|jpeg|png|gif|webp|heic|heif))>$",
    re.IGNORECASE,
)
# "image omitted" — chat exported without media; nothing to process
_MEDIA_OMITTED = re.compile(r"^[‎‏]*(?:image|video|audio|document) omitted$", re.IGNORECASE)


@dataclass
class ChatItem:
    """A single extracted item: either a photo or a hyperlink."""

    type: str  # "photo" or "link"
    sender: str
    date: datetime
    content: str  # absolute file path for photos, URL for links
    file_hash: Optional[str] = field(default=None)  # SHA-256 hex digest (photos only)


def _parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """
    Try multiple strptime formats to accommodate regional date ordering
    (M/D/Y vs D/M/Y) and 12 h vs 24 h clocks used across Android and iOS.
    Returns None if no format matches.
    """
    combined = f"{date_str} {time_str.strip()}"
    formats = [
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


def _sha256(path: str) -> str:
    """Compute a SHA-256 hex digest for the given file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _match_media(body: str) -> Optional[str]:
    """
    Return the media filename if the message body is a WhatsApp attachment
    line, or None if it is not.
    """
    m = _ATTACHED_SUFFIX.match(body) or _ATTACHED_BRACKET.match(body)
    return m.group(1) if m else None


def _parse_lines(lines: list[str]) -> list[tuple[Optional[datetime], str, str]]:
    """
    Convert raw chat lines into (datetime, sender, body) tuples, merging
    multi-line messages back into their original message.
    """
    messages: list[tuple[Optional[datetime], str, str]] = []
    current: Optional[tuple[Optional[datetime], str, str]] = None

    for raw in lines:
        line = raw.rstrip("\n")
        matched = False
        for pattern in MESSAGE_PATTERNS:
            m = pattern.match(line)
            if m:
                date_str, time_str, sender, body = m.groups()
                dt = _parse_datetime(date_str, time_str)
                if current is not None:
                    messages.append(current)
                current = (dt, sender.strip(), body.strip())
                matched = True
                break
        if not matched and current is not None:
            # Continuation line of the previous message
            current = (current[0], current[1], current[2] + "\n" + line)

    if current is not None:
        messages.append(current)

    return messages


def parse_chat_zip(zip_path: str) -> tuple[list[ChatItem], str]:
    """
    Extract a WhatsApp chat zip and return all photos and links found in it.

    Returns:
        (items, temp_dir) where *temp_dir* is the path to a temporary
        directory containing the extracted files.  The caller is responsible
        for deleting it (e.g. with shutil.rmtree) when done.

    Raises:
        ValueError: if no .txt chat file is found in the zip.
        zipfile.BadZipFile: if the file is not a valid zip.
    """
    temp_dir = tempfile.mkdtemp(prefix="wa_export_")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(temp_dir)

    # Locate the chat transcript — usually the only .txt in the zip
    txt_files = list(Path(temp_dir).glob("*.txt"))
    if not txt_files:
        raise ValueError(f"No .txt chat file found inside {zip_path}")
    chat_txt = txt_files[0]

    # Build a lookup of every image file extracted from the zip (lowercase name → path)
    media_map: dict[str, str] = {
        f.name.lower(): str(f)
        for f in Path(temp_dir).iterdir()
        if f.suffix.lower() in IMAGE_EXTENSIONS
    }

    with open(chat_txt, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    messages = _parse_lines(lines)
    items: list[ChatItem] = []

    for dt, sender, body in messages:
        if dt is None:
            continue  # skip un-parseable timestamps (e.g. system messages)

        # Skip "image omitted" lines — no actual file to process
        if _MEDIA_OMITTED.match(body):
            continue

        filename = _match_media(body)
        if filename:
            path = media_map.get(filename.lower())
            if path:
                items.append(
                    ChatItem(
                        type="photo",
                        sender=sender,
                        date=dt,
                        content=path,
                        file_hash=_sha256(path),
                    )
                )
            # If filename not in media_map the zip was likely exported without media
        else:
            # Extract every URL found in the message body
            for url in URL_PATTERN.findall(body):
                # Strip trailing punctuation that the regex may have captured
                url = url.rstrip(".,;!?)")
                items.append(
                    ChatItem(
                        type="link",
                        sender=sender,
                        date=dt,
                        content=url,
                    )
                )

    return items, temp_dir
