import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QDialogButtonBox, QMessageBox, QPushButton,
)
from PyQt6.QtCore import Qt

BROWSERS = ["Firefox", "Chrome", "Brave", "Edge"]

CHROMIUM_BROWSERS = {"chrome", "brave", "edge"}

_WIN_DPAPI_HELP = (
    "Chromium-based browsers (Edge, Chrome, Brave) encrypt cookies on Windows "
    "using DPAPI + AES-256-GCM.\n\n"
    "Required packages are not installed. Run:\n\n"
    "    pip install pywin32 pycryptodome\n\n"
    "Then restart the application and try again."
)


def _check_win_crypto():
    """Return an error string if Windows crypto deps are missing, else None."""
    if sys.platform != "win32":
        return None
    missing = []
    try:
        import win32crypt  # noqa: F401
    except ImportError:
        missing.append("pywin32")
    try:
        from Crypto.Cipher import AES  # noqa: F401
    except ImportError:
        missing.append("pycryptodome")
    if missing:
        return f"Missing: {', '.join(missing)}\n\n" + _WIN_DPAPI_HELP
    return None


class BrowserImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Cookies from Browser")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._cookies = []

        layout = QVBoxLayout(self)

        form_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Browser:"))
        self._browser_combo = QComboBox()
        self._browser_combo.addItems(BROWSERS)
        self._browser_combo.currentTextChanged.connect(self._on_browser_changed)
        row1.addWidget(self._browser_combo)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Domain filter (optional):"))
        self._domain_edit = QLineEdit()
        self._domain_edit.setPlaceholderText("e.g. github.com — leave blank for all")
        row2.addWidget(self._domain_edit)
        form_layout.addLayout(row2)

        layout.addLayout(form_layout)

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

        # Show hint immediately if deps are missing for the default browser
        self._on_browser_changed(self._browser_combo.currentText())

    def _on_browser_changed(self, browser_text):
        if browser_text.lower() in CHROMIUM_BROWSERS:
            err = _check_win_crypto()
            if err:
                self._status_label.setText(
                    "Note: pywin32 / pycryptodome required for this browser on Windows."
                )
                self._import_btn.setEnabled(False)
                return
        self._status_label.setText("")
        self._import_btn.setEnabled(True)

    def _do_import(self):
        try:
            import browser_cookie3
        except ImportError:
            QMessageBox.critical(self, "Missing Library",
                                 "browser-cookie3 is not installed.\n\nRun: pip install browser-cookie3")
            return

        browser = self._browser_combo.currentText().lower()
        domain = self._domain_edit.text().strip() or None

        # Pre-flight check for Windows crypto deps
        if browser in CHROMIUM_BROWSERS:
            err = _check_win_crypto()
            if err:
                QMessageBox.critical(self, "Missing Dependencies", err)
                return

        self._status_label.setText("Importing, please wait…")
        self._import_btn.setEnabled(False)

        try:
            func_map = {
                "firefox": browser_cookie3.firefox,
                "chrome": browser_cookie3.chrome,
                "brave": browser_cookie3.brave,
                "edge": browser_cookie3.edge,
            }
            fn = func_map[browser]
            kwargs = {"domain_name": domain} if domain else {}
            jar = fn(**kwargs)

            self._cookies = []
            for c in jar:
                expiry = str(int(c.expires)) if c.expires else "0"
                self._cookies.append({
                    "domain": c.domain or "",
                    "flag": "TRUE" if getattr(c, "domain_specified", False) else "FALSE",
                    "path": c.path or "/",
                    "secure": "TRUE" if c.secure else "FALSE",
                    "expiry": expiry,
                    "name": c.name or "",
                    "value": c.value or "",
                })

            count = len(self._cookies)
            if count == 0:
                self._status_label.setText("No cookies found. Check the browser or domain filter.")
                self._import_btn.setEnabled(True)
                return

            self._status_label.setText(f"Found {count} cookies.")
            self.accept()

        except PermissionError:
            self._status_label.setText(
                "Permission denied — close the browser completely and try again."
            )
            self._import_btn.setEnabled(True)
        except Exception as e:
            msg = str(e)
            if "key" in msg.lower() and "decrypt" in msg.lower():
                detail = _WIN_DPAPI_HELP if sys.platform == "win32" else msg
                QMessageBox.critical(self, "Decryption Error", detail)
            else:
                QMessageBox.critical(self, "Import Error", msg)
            self._import_btn.setEnabled(True)

    def get_cookies(self):
        return self._cookies
