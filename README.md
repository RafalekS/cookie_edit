# Cookie Editor

A desktop GUI application for viewing and editing browser cookie files.
Built with Python 3 and PyQt6.

## Supported formats

| Format | Extension | Notes |
|--------|-----------|-------|
| Netscape / cookies.txt | `.txt` | Standard format used by curl, wget, yt-dlp |
| JSON (Cookie-Editor) | `.json` | Compatible with the Cookie-Editor browser extension |
| Header String | `.txt` | Single-line `name=value; name2=value2` HTTP header |

Format is auto-detected on open. Files can be converted between formats via **Save As**.

## Features

- View and edit cookies in a sortable, resizable table
- Add, edit (double-click), and delete cookie rows
- Filter by domain, cookie name, or both — comma-separated terms use OR logic
- Save filter presets (Quick Filter menu)
- Export selected domains to a new file (any format)
- Append cookies from a second file with domain selection
- Import cookies directly from an installed browser (Chrome, Brave, Edge, Firefox)
- Unsaved-changes indicator in title bar
- Column order, widths, and sort state persist across sessions

## Requirements

```
PyQt6 >= 6.4.0
browser-cookie3 >= 0.20.0
pywin32 >= 306          # Windows only
pycryptodome >= 3.18.0  # Windows only (Chromium cookie decryption)
```

Install:

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

### Browser import (Windows)

Chrome, Brave, and Edge cookies are decrypted using Windows DPAPI + AES-256-GCM directly,
without relying on browser-cookie3 for the key step (which breaks on newer browser versions).
Firefox cookies are read directly from the SQLite database (no encryption).

### Cookie formats

**Netscape** — 7 tab-separated columns:
```
domain  flag  path  secure  expiry  name  value
```
Comment lines (`#`) are preserved on save.

**JSON** — Cookie-Editor compatible array:
```json
[{"domain": "example.com", "name": "session", "value": "abc123", ...}]
```

**Header String** — single line, name and value only:
```
session=abc123; user_id=42; theme=dark
```

## Configuration

All settings (window geometry, last directory, column state, saved filters) are stored in
`config/config.json`, which is excluded from version control.

## License

See [LICENSE](LICENSE) for details.
