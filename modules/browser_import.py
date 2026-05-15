import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QDialogButtonBox, QMessageBox, QPushButton,
)
from PyQt6.QtCore import Qt

BROWSERS = ["Firefox", "Chrome", "Brave", "Edge"]

_WIN_DPAPI_HELP = (
    "Chromium-based browsers (Edge, Chrome, Brave) encrypt cookies on Windows "
    "using DPAPI + AES-256-GCM.\n\n"
    "Install the required packages and restart the application:\n\n"
    "    pip install pywin32 pycryptodome"
)


def _is_dpapi_error(exc):
    msg = str(exc).lower()
    return "key" in msg and "decrypt" in msg


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
        try:
            import browser_cookie3
        except ImportError:
            QMessageBox.critical(self, "Missing Library",
                                 "browser-cookie3 is not installed.\n\nRun: pip install browser-cookie3")
            return

        browser = self._browser_combo.currentText().lower()
        domain = self._domain_edit.text().strip() or None

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
            if sys.platform == "win32" and _is_dpapi_error(e):
                QMessageBox.critical(self, "Decryption Error", _WIN_DPAPI_HELP)
            else:
                QMessageBox.critical(self, "Import Error", str(e))
            self._import_btn.setEnabled(True)

    def get_cookies(self):
        return self._cookies
