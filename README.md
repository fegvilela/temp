# whatsapp-refs

CLI tool that processes exported WhatsApp chat zips and saves photos and links to a Notion database, with AI-powered categorization for home interior references.

---

## Features

- Parses WhatsApp `.zip` exports (Android and iOS formats)
- Extracts all shared photos and links
- Categorizes each item using **Gemini 1.5 Flash** (free tier):
  - Photos → vision analysis
  - Links → title + description analysis
- Pushes new items to a **Notion database** with metadata
- Deduplicates against existing entries (links by URL, photos by SHA-256 hash)
- Prints a summary at the end

**Categories:** Living Room · Kitchen · Bedroom · Bathroom · Outdoor · Dining Room · Home Office · Other

---

## Prerequisites

- Python 3.11+
- A [Google AI Studio](https://aistudio.google.com/app/apikey) account (free) → Gemini API key
- A Notion account with an [integration token](https://www.notion.so/my-integrations)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd whatsapp-refs
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```
GEMINI_API_KEY=your_gemini_api_key_here
NOTION_API_KEY=secret_your_notion_integration_token_here
NOTION_DATABASE_ID=your_notion_database_id_here
```

### 3. Set up the Notion database

Create a new database in Notion with these **exact** property names and types:

| Property  | Type            | Notes                                        |
|-----------|-----------------|----------------------------------------------|
| Name      | Title           | Auto-created on every Notion database        |
| Type      | Select          | Options: `Photo`, `Link`                     |
| Sender    | Text            |                                              |
| Date      | Date            |                                              |
| Category  | Select          | Options: the 8 room categories listed above  |
| URL       | URL             | Populated for links only                     |
| Filename  | Text            | Populated for photos only                    |
| Hash      | Text            | SHA-256 hash (used for dedup; can be hidden) |
| Thumbnail | Files & media   | og:image for links (optional)                |

Then share the database with your integration:
1. Open the database → click **Share** (top right)
2. Invite your integration by name
3. Grant **Edit content** access

The **Database ID** is the 32-character hex string in the database URL:
```
https://www.notion.so/myworkspace/<DATABASE_ID>?v=...
```

---

## Usage

Export a WhatsApp group chat:
- **Android:** Open chat → ⋮ → More → Export chat → With Media (or Without)
- **iOS:** Open chat → Contact/Group name → Export Chat → With Media (or Without)

Then run:

```bash
python process.py --zip ~/Downloads/WhatsApp\ Chat.zip
```

### Example output

```
Parsing /home/user/Downloads/WhatsApp Chat.zip …
  Found 42 photo(s) and 17 link(s) in the export.
Fetching existing Notion entries for deduplication …
  Notion has 5 existing link(s) and 10 existing photo(s).
  [1/59] Skipping duplicate link: https://www.houzz.com/…
  [2/59] Processing photo from Alice (2024-03-15) …
        Category: Kitchen
  [3/59] Processing link from Bob (2024-03-15) …
        Title:    10 Modern Kitchen Ideas for 2024
        Category: Kitchen
  …

──────────────────────────────────────────────────
  34 new item(s) added to Notion
  25 duplicate(s) skipped
──────────────────────────────────────────────────
```

---

## Project structure

```
whatsapp-refs/
├── process.py        # CLI entrypoint — orchestrates everything
├── parser.py         # WhatsApp zip/txt parsing
├── categorizer.py    # Gemini API categorization (vision + text)
├── notion_client.py  # Notion REST API read/write
├── dedup.py          # Deduplication logic
├── .env.example      # Credential template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Notes

- **Rate limits:** Gemini free tier allows ~15 requests/minute. The tool inserts a short delay between calls. For large exports (100+ items) this may take a few minutes.
- **Photos are not uploaded to Notion** — only the filename and hash are stored. The actual image stays on your machine. If you want to view images in Notion, consider uploading them to a cloud service and storing the URL instead.
- **Media omitted exports:** If you chose "Without Media" when exporting, photo entries will have no file to analyze and will be skipped automatically.
- **notion_client.py** calls the Notion REST API directly via `requests` rather than importing the `notion-client` SDK, because the SDK's module name (`notion_client`) would conflict with this file's own module name.

---

## License

MIT
