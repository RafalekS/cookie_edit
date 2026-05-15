# Task: cookie_edit

## Objective
Create a Python desktop GUI application for editing browser cookie files.
Supported formats:
Netscape/cookies.txt (tab-separated, 7 columns)
JSON (array of cookie objects, as exported by browser extensions like EditThisCookie, Cookie-Editor)
Header string (single-line Cookie: name=value; name2=value2 format)
Requirements:
Use Python 3.1x with PyQt6
Load a cookie file via file dialog, auto-detect format on open, or allow user to manually select format
Display cookies in a sortable, scrollable table using QTableView with a custom model, with columns: domain, flag, path, secure, expiry, name, value (populate what is available per format, leave blank where not applicable)
Allow the user to: 
Add a new cookie row
Edit any field of an existing row (double-click opens edit dialog)
Delete one or more selected rows
Filter/search by domain or cookie name
Save back to the original format
Save As with format conversion (e.g. export Netscape as JSON, JSON as header string, etc.)
Preserve comment lines (lines starting with #) when working with Netscape format
Validate fields before saving: 
Netscape: expiry must be a unix timestamp integer, flag/secure must be TRUE/FALSE
JSON: output must be valid JSON
Header string: output must be valid single-line cookie header
Show unsaved changes indicator in title bar
Show current file path and detected format in status bar
All configurable values (window size, default directory, last opened file) stored in config.json, never hardcoded in the program code
Browser Cookie Extraction:
Add a menu option to import cookies directly from an installed browser
Support the following browsers: Chrome, Brave, Edge (all Chromium-based, use DPAPI + AES-256-GCM decryption on Windows), and Firefox (plain SQLite, no decryption)
Use the browser-cookie3 library for extraction
Allow the user to select which browser and optionally filter by domain
Imported cookies load directly into the editor table
User can then save/export in any supported format
Tech stack: Python 3.1x, PyQt6, browser-cookie3, pywin32, pycryptodome, JSON for config.
Reference Documentation:
Netscape cookies.txt format: https://curl.se/docs/http-cookies.html and https://everything.curl.dev/http/cookies/fileformat.html
JSON cookie format: https://cookie-editor.com/
HTTP Cookie header specification (RFC 6265): https://www.rfc-editor.org/rfc/rfc6265
browser-cookie3 library: https://github.com/borisbabic/browser_cookie3
Deliver:
main.py — application entry point and logic
config.json — default config file
requirements.txt

Very Important - Use coding skill for this project!

## Instructions
Complete the task described above autonomously. When finished, provide a summary of what was accomplished.

## Constraints
- Commit changes when task is complete

## Success Criteria
- All requirements from the objective are met
- Code is clean and documented
- No errors or warnings
