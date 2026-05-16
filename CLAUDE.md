# CLAUDE.md — Cookie Editor

Project notes for AI assistants working on this codebase.

## Architecture

```
main.py                     # MainWindow, entry point
modules/
  cookie_formats.py         # parse/save for all 3 formats + format detection
  cookie_model.py           # QAbstractTableModel + QSortFilterProxyModel
  edit_dialog.py            # single-cookie edit dialog
  browser_import.py         # browser cookie import dialog
  win_cookies.py            # Windows DPAPI + AES-256-GCM Chromium decryption
  domain_export.py          # export-by-domain dialog
  append_dialog.py          # append-from-file domain picker
  filter_dialog.py          # saved filter create/edit dialog
  utils.py                  # config load/save, validation helpers
config/
  assets/cookie_edit.png    # app icon
config/config.json          # runtime config (gitignored)
```

## Key conventions

- **No `setStretchLastSection`**. All columns use `QHeaderView.ResizeMode.Interactive`.
- **Sorting enabled after data load**, not during.
- **State restored once at startup** (`_restore_table_state`), never inside populate loops.
- **Debounced config save** via `QTimer` (500 ms, singleShot).
- Column widths for hidden columns are preserved in config (hidden columns report 0 from Qt).

## Cookie data model

Each cookie is a plain `dict` with keys:
`domain`, `flag`, `path`, `secure`, `expiry`, `name`, `value`

JSON-imported cookies also carry `_json_httpOnly`, `_json_sameSite`, `_json_storeId`,
`_json_session` metadata keys that are preserved on save.

## Format detection

`detect_format()` in `cookie_formats.py`:
1. Read first 4096 chars, lstrip
2. If first char is `[` or `{` → try `json.load()` on full file → `"json"`
3. If starts with `#` or first line has tab → `"netscape"`
4. If first line has `;` and `=` → `"header"`
5. Fallback → `"netscape"`

## Windows Chromium decryption

`win_cookies.py` bypasses browser-cookie3 for Windows Chromium browsers.
Uses `win32crypt.CryptUnprotectData` to unwrap the AES master key from `Local State`,
then `AES.MODE_GCM` to decrypt individual cookie values.
Format: `3-byte tag | 12-byte nonce | ciphertext | 16-byte auth tag`.

## Config keys

`window`, `default_directory`, `last_opened_file`, `column_widths`, `column_order`,
`sort_column`, `sort_order`, `saved_filters`
