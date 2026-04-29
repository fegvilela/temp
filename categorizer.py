"""
Gemini-powered categorization for home interior photos and links.

Uses gemini-1.5-flash (free tier) with vision for photos and text-only
prompting for links. Falls back to "Other" on any API error.
"""

import time
from pathlib import Path

import google.generativeai as genai
import PIL.Image


CATEGORIES = [
    "Living Room",
    "Kitchen",
    "Bedroom",
    "Bathroom",
    "Outdoor",
    "Dining Room",
    "Home Office",
    "Other",
]

_CATEGORY_LIST = ", ".join(CATEGORIES)

_PHOTO_PROMPT = (
    "You are a home interior design classifier. "
    "Look at this image and decide which single room or area it shows. "
    f"Choose ONLY from: {_CATEGORY_LIST}. "
    "Reply with EXACTLY the category name and nothing else."
)

_LINK_PROMPT_TEMPLATE = (
    "You are a home interior design classifier. "
    "Based on the following information about a web page, decide which room "
    "or area it is most likely related to. "
    f"Choose ONLY from: {_CATEGORY_LIST}. "
    "Reply with EXACTLY the category name and nothing else.\n\n"
    "URL: {url}\n"
    "Title: {title}\n"
    "Description: {description}"
)

_MODEL_NAME = "gemini-1.5-flash"

# Free-tier rate limit is ~15 RPM; a 0.5 s floor keeps bursts safe
_MIN_DELAY_SECONDS = 0.5
# Max retries on transient quota / server errors
_MAX_RETRIES = 3


def _normalize_category(raw: str) -> str:
    """
    Map the model's raw text response to one of the known category strings.
    Falls back to "Other" if no match is found.
    """
    clean = raw.strip().strip(".")
    for cat in CATEGORIES:
        if cat.lower() == clean.lower():
            return cat
    # Partial match fallback (e.g. model replied "living room" lowercase)
    for cat in CATEGORIES:
        if cat.lower() in clean.lower():
            return cat
    return "Other"


def _call_with_retry(model: genai.GenerativeModel, content: list, label: str) -> str:
    """
    Call model.generate_content with exponential back-off on transient errors.
    Returns the raw text from the first successful response.
    """
    delay = 2.0
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = model.generate_content(content)
            return response.text
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            print(f"  Gemini error for {label} (attempt {attempt}/{_MAX_RETRIES}): {exc}. Retrying in {delay}s…")
            time.sleep(delay)
            delay *= 2
    # Unreachable, but satisfies type checkers
    return "Other"


def categorize_photo(image_path: str, api_key: str) -> str:
    """
    Use Gemini vision to categorize a home interior photo.

    Args:
        image_path: Absolute path to the image file.
        api_key: Gemini API key.

    Returns:
        One of the CATEGORIES strings. Returns "Other" on any failure.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(_MODEL_NAME)

    filename = Path(image_path).name
    try:
        img = PIL.Image.open(image_path)
        raw = _call_with_retry(model, [_PHOTO_PROMPT, img], filename)
        category = _normalize_category(raw)
        time.sleep(_MIN_DELAY_SECONDS)
        return category
    except Exception as exc:
        print(f"  Warning: could not categorize photo {filename}: {exc}. Defaulting to 'Other'.")
        return "Other"


def categorize_link(url: str, title: str, description: str, api_key: str) -> str:
    """
    Use Gemini to categorize a link based on its URL, title, and description.

    Args:
        url: The page URL.
        title: Page title (from <title> or og:title).
        description: Page description (from og:description or meta description).
        api_key: Gemini API key.

    Returns:
        One of the CATEGORIES strings. Returns "Other" on any failure.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(_MODEL_NAME)

    prompt = _LINK_PROMPT_TEMPLATE.format(
        url=url,
        title=title or "(no title)",
        description=description or "(no description)",
    )
    try:
        raw = _call_with_retry(model, [prompt], url)
        category = _normalize_category(raw)
        time.sleep(_MIN_DELAY_SECONDS)
        return category
    except Exception as exc:
        print(f"  Warning: could not categorize link {url}: {exc}. Defaulting to 'Other'.")
        return "Other"
