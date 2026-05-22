from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPlainTextEdit, QDialogButtonBox, QPushButton, QFileDialog,
)
from PyQt6.QtCore import Qt

BROWSER_LABELS = ["Brave", "Chrome", "Edge", "Firefox"]
BROWSER_KEYS   = ["brave", "chrome", "edge", "firefox"]

DEFAULT_WORKFLOW_CONFIG = {
    "browser": "brave",
    "all_cookies_path": "",
    "filtered_cookies_path": "",
    "filter_name": "",
    "post_save_commands": [],
}


class WorkflowConfigDialog(QDialog):
    """Configure the distribution workflow parameters."""

    def __init__(self, wf_config, saved_filter_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Distribution Workflow")
        self.setMinimumSize(620, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        # Browser
        browser_row = QHBoxLayout()
        browser_row.addWidget(QLabel("Import from browser:"))
        self._browser = QComboBox()
        self._browser.addItems(BROWSER_LABELS)
        key = wf_config.get("browser", "brave").lower()
        self._browser.setCurrentIndex(BROWSER_KEYS.index(key) if key in BROWSER_KEYS else 0)
        browser_row.addWidget(self._browser)
        browser_row.addStretch()
        layout.addLayout(browser_row)

        # All cookies path
        layout.addWidget(QLabel("Save ALL cookies to (all.txt):"))
        all_row = QHBoxLayout()
        self._all_path = QLineEdit(wf_config.get("all_cookies_path", ""))
        self._all_path.setPlaceholderText("e.g. Y:\\Downloads\\metube\\cookies\\all.txt")
        all_row.addWidget(self._all_path)
        all_browse = QPushButton("Browse…")
        all_browse.clicked.connect(lambda: self._browse(self._all_path))
        all_row.addWidget(all_browse)
        layout.addLayout(all_row)

        # Filtered cookies path
        layout.addWidget(QLabel("Save FILTERED cookies to (cookies.txt):"))
        filt_row = QHBoxLayout()
        self._filt_path = QLineEdit(wf_config.get("filtered_cookies_path", ""))
        self._filt_path.setPlaceholderText("e.g. Y:\\Downloads\\metube\\cookies\\cookies.txt")
        filt_row.addWidget(self._filt_path)
        filt_browse = QPushButton("Browse…")
        filt_browse.clicked.connect(lambda: self._browse(self._filt_path))
        filt_row.addWidget(filt_browse)
        layout.addLayout(filt_row)

        # Filter to apply
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Apply saved filter:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(saved_filter_names)
        current_name = wf_config.get("filter_name", "")
        if current_name in saved_filter_names:
            self._filter_combo.setCurrentText(current_name)
        filter_row.addWidget(self._filter_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Post-save commands
        layout.addWidget(QLabel(
            "Post-save commands — one per line:\n"
            "  {all_path} = all cookies file path\n"
            "  {filtered_path} = filtered cookies file path"
        ))
        self._commands = QPlainTextEdit()
        self._commands.setPlaceholderText(
            'curl -X POST http://192.168.0.166:7799/cookies -H "X-API-Key: changeme" '
            '-H "Content-Type: text/plain" --data-binary @{filtered_path}\n'
            'curl -X POST http://192.168.0.166:7799/cookies/sync-stash -H "X-API-Key: changeme"'
        )
        self._commands.setPlainText("\n".join(wf_config.get("post_save_commands", [])))
        self._commands.setMinimumHeight(100)
        layout.addWidget(self._commands)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self, line_edit):
        path, _ = QFileDialog.getSaveFileName(
            self, "Select File", line_edit.text() or "",
            "Text Files (*.txt);;All Files (*)"
        )
        if path:
            line_edit.setText(path)

    def get_config(self):
        raw_cmds = self._commands.toPlainText()
        commands = [l.strip() for l in raw_cmds.splitlines() if l.strip()]
        return {
            "browser":              BROWSER_KEYS[self._browser.currentIndex()],
            "all_cookies_path":     self._all_path.text().strip(),
            "filtered_cookies_path": self._filt_path.text().strip(),
            "filter_name":          self._filter_combo.currentText(),
            "post_save_commands":   commands,
        }
