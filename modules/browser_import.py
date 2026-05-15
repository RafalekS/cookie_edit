from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QDialogButtonBox, QMessageBox, QPushButton,
)
from PyQt6.QtCore import Qt

BROWSERS = ["Firefox", "Chrome", "Brave", "Edge"]


class BrowserImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Cookies from Browser")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._cookies = []

        layout = QVBoxLayout(self)

        form_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Browser:"))
        self._browser_combo = QComboBox()
        self._browser_combo.addItems(BROWSERS)
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

    def _do_import(self):
        try:
            import browser_cookie3
        except ImportError:
            QMessageBox.critical(self, "Missing Library", "browser-cookie3 is not installed.")
            return

        browser = self._browser_combo.currentText().lower()
        domain = self._domain_edit.text().strip() or None

        self._status_label.setText("Importing, please wait...")
        self._import_btn.setEnabled(False)

        try:
            func_map = {
                "firefox": browser_cookie3.firefox,
                "chrome": browser_cookie3.chrome,
                "brave": browser_cookie3.brave,
                "edge": browser_cookie3.edge,
            }
            fn = func_map.get(browser)
            if fn is None:
                self._status_label.setText("Unknown browser.")
                return

            kwargs = {}
            if domain:
                kwargs["domain_name"] = domain

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
                "Permission denied — close the browser and try again, "
                "or the profile database is locked."
            )
            self._import_btn.setEnabled(True)
        except Exception as e:
            self._status_label.setText(f"Error: {e}")
            self._import_btn.setEnabled(True)

    def get_cookies(self):
        return self._cookies
