import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QDialogButtonBox, QMessageBox, QPushButton,
)
from PyQt6.QtCore import Qt

BROWSERS = ["Firefox", "Chrome", "Brave", "Edge"]
CHROMIUM_BROWSERS = {"chrome", "brave", "edge"}


class BrowserImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Cookies from Browser")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._cookies = []

        layout = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Browser:"))
        self._browser_combo = QComboBox()
        self._browser_combo.addItems(BROWSERS)
        row1.addWidget(self._browser_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Domain filter (optional):"))
        self._domain_edit = QLineEdit()
        self._domain_edit.setPlaceholderText("e.g. github.com — leave blank for all")
        row2.addWidget(self._domain_edit)
        layout.addLayout(row2)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        btn_box = QDialogButtonBox()
        self._import_btn = QPushButton("Import Cookies")
        cancel_btn = QPushButton("Cancel")
        btn_box.addButton(self._import_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        self._import_btn.clicked.connect(self._do_import)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(btn_box)

    def _do_import(self):
        browser = self._browser_combo.currentText().lower()
        domain = self._domain_edit.text().strip() or None

        self._status_label.setText("Importing, please wait…")
        self._import_btn.setEnabled(False)

        try:
            if sys.platform == "win32" and browser in CHROMIUM_BROWSERS:
                cookies = self._import_win_chromium(browser, domain)
            else:
                cookies = self._import_via_browser_cookie3(browser, domain)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))
            self._status_label.setText("")
            self._import_btn.setEnabled(True)
            return

        if not cookies:
            self._status_label.setText("No cookies found. Check the browser or domain filter.")
            self._import_btn.setEnabled(True)
            return

        self._cookies = cookies
        self._status_label.setText(f"Found {len(cookies)} cookies.")
        self.accept()

    def _import_win_chromium(self, browser, domain):
        """Direct SQLite + DPAPI + AES-GCM extraction — no browser_cookie3."""
        try:
            import win32crypt  # noqa: F401 — check early for clear error
        except ImportError:
            raise ImportError(
                "pywin32 is required for Chromium browser import on Windows.\n\n"
                "Run:  pip install pywin32"
            )

        from modules.win_cookies import extract
        return extract(browser, domain_filter=domain)

    def _import_via_browser_cookie3(self, browser, domain):
        """Use browser_cookie3 — for Firefox on any platform, or Chromium on Linux/Mac."""
        try:
            import browser_cookie3
        except ImportError:
            raise ImportError(
                "browser-cookie3 is not installed.\n\nRun:  pip install browser-cookie3"
            )

        func_map = {
            "firefox": browser_cookie3.firefox,
            "chrome":  browser_cookie3.chrome,
            "brave":   browser_cookie3.brave,
            "edge":    browser_cookie3.edge,
        }
        fn = func_map.get(browser)
        if fn is None:
            raise ValueError(f"Unknown browser: {browser!r}")

        kwargs = {"domain_name": domain} if domain else {}
        jar = fn(**kwargs)

        cookies = []
        for c in jar:
            expiry = str(int(c.expires)) if c.expires else "0"
            cookies.append({
                "domain": c.domain or "",
                "flag": "TRUE" if getattr(c, "domain_specified", False) else "FALSE",
                "path": c.path or "/",
                "secure": "TRUE" if c.secure else "FALSE",
                "expiry": expiry,
                "name": c.name or "",
                "value": c.value or "",
            })
        return cookies

    def get_cookies(self):
        return self._cookies
