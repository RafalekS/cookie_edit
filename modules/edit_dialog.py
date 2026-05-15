from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class CookieEditDialog(QDialog):
    def __init__(self, cookie=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Cookie" if cookie else "Add Cookie")
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        cookie = cookie or {}
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._fields = {}

        self._fields["domain"] = QLineEdit(cookie.get("domain", ""))
        self._fields["domain"].setPlaceholderText(".example.com")
        layout.addRow("Domain:", self._fields["domain"])

        self._fields["flag"] = QComboBox()
        self._fields["flag"].addItems(["TRUE", "FALSE"])
        self._fields["flag"].setCurrentIndex(
            0 if cookie.get("flag", "FALSE").upper() == "TRUE" else 1
        )
        layout.addRow("Flag (domain covers subdomains):", self._fields["flag"])

        self._fields["path"] = QLineEdit(cookie.get("path", "/"))
        layout.addRow("Path:", self._fields["path"])

        self._fields["secure"] = QComboBox()
        self._fields["secure"].addItems(["TRUE", "FALSE"])
        self._fields["secure"].setCurrentIndex(
            0 if cookie.get("secure", "FALSE").upper() == "TRUE" else 1
        )
        layout.addRow("Secure (HTTPS only):", self._fields["secure"])

        self._fields["expiry"] = QLineEdit(cookie.get("expiry", "0"))
        self._fields["expiry"].setPlaceholderText("Unix timestamp (e.g. 1893456000)")
        layout.addRow("Expiry (Unix timestamp):", self._fields["expiry"])

        self._fields["name"] = QLineEdit(cookie.get("name", ""))
        layout.addRow("Name:", self._fields["name"])

        self._fields["value"] = QLineEdit(cookie.get("value", ""))
        layout.addRow("Value:", self._fields["value"])

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_cookie(self):
        return {
            "domain": self._fields["domain"].text(),
            "flag": self._fields["flag"].currentText(),
            "path": self._fields["path"].text(),
            "secure": self._fields["secure"].currentText(),
            "expiry": self._fields["expiry"].text(),
            "name": self._fields["name"].text(),
            "value": self._fields["value"].text(),
        }
