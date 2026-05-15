# Cookie Editor — TODO

## Status: Initial Implementation Complete — Awaiting User Test

### Delivered
- [x] main.py — main window, menus, toolbar, all file/edit/import ops
- [x] modules/cookie_formats.py — parse/save Netscape, JSON, Header formats
- [x] modules/cookie_model.py — QAbstractTableModel + QSortFilterProxyModel
- [x] modules/edit_dialog.py — add/edit cookie dialog
- [x] modules/browser_import.py — import from Firefox/Chrome/Brave/Edge
- [x] modules/utils.py — config load/save, field validation
- [x] config/config.json — default config (window, paths, column state)
- [x] requirements.txt

### Pending / Needs Test
- [ ] User must test all features on target machine (Raspberry Pi)
- [ ] Verify browser import works (Firefox most likely; Chromium needs keyring)
- [ ] Confirm Netscape comment preservation round-trip
- [ ] Confirm JSON extra fields (httpOnly, sameSite, storeId) preserved on save
- [ ] Confirm column order/width/sort persist across restarts

### Known Constraints
- DPAPI decryption (Windows-only) not available on Linux — Chromium browsers
  may fail if cookie DB is encrypted with a key stored in the OS keyring and
  no keyring daemon is running (gnome-keyring / kwallet). Firefox is plain SQLite.
- browser-cookie3 requires the browser to be closed (DB lock).

### Mistakes & Fixes
- (none yet — fill in after test)
