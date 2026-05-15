from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QComboBox, QDialogButtonBox, QMessageBox,
    QPushButton,
)
from PyQt6.QtCore import Qt

SCOPE_LABELS = ["Domain", "Cookie Name", "Domain + Name"]
SCOPE_KEYS   = ["domain", "name", "both"]


class FilterEditDialog(QDialog):
    """Create or edit a saved filter."""

    def __init__(self, filter_data=None, parent=None):
        super().__init__(parent)
        is_new = filter_data is None
        self.setWindowTitle("New Saved Filter" if is_new else "Edit Saved Filter")
        self.setMinimumSize(440, 380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Filter name:"))
        self._name = QLineEdit(filter_data.get("name", "") if filter_data else "")
        self._name.setPlaceholderText("e.g.  yt-dlp sites")
        layout.addWidget(self._name)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Search in:"))
        self._scope = QComboBox()
        self._scope.addItems(SCOPE_LABELS)
        if filter_data:
            idx = SCOPE_KEYS.index(filter_data.get("scope", "domain"))
            self._scope.setCurrentIndex(idx)
        scope_row.addWidget(self._scope)
        scope_row.addStretch()
        layout.addLayout(scope_row)

        layout.addWidget(QLabel("Search terms — one per line  (or comma-separated):"))
        self._terms = QPlainTextEdit()
        self._terms.setPlaceholderText(
            "xvideos.com\nxhamster.com\npornhub.com"
        )
        if filter_data:
            terms = [t.strip() for t in filter_data.get("text", "").split(",") if t.strip()]
            self._terms.setPlainText("\n".join(terms))
        layout.addWidget(self._terms)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        f = self.get_filter()
        if not f["name"]:
            QMessageBox.warning(self, "Validation", "Please enter a filter name.")
            return
        if not f["text"]:
            QMessageBox.warning(self, "Validation", "Please enter at least one search term.")
            return
        self.accept()

    def get_filter(self):
        scope = SCOPE_KEYS[self._scope.currentIndex()]
        raw = self._terms.toPlainText().replace(",", "\n")
        terms = [t.strip() for t in raw.splitlines() if t.strip()]
        return {
            "name":  self._name.text().strip(),
            "scope": scope,
            "text":  ", ".join(terms),
        }
