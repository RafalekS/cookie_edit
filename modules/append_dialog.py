from collections import defaultdict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QDialogButtonBox, QPushButton, QApplication,
)
from PyQt6.QtCore import Qt


class DomainImportDialog(QDialog):
    """Pick which domains to import from a parsed source file."""

    def __init__(self, cookies, source_path, source_fmt, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Append from File — Select Domains")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        screen_h = QApplication.primaryScreen().availableGeometry().height()
        self.setMinimumSize(480, min(520, screen_h - 80))
        self.setMaximumHeight(screen_h - 80)

        self._cookies = cookies
        self._domain_map = defaultdict(list)
        for c in cookies:
            self._domain_map[c.get("domain", "")].append(c)
        self._sorted_domains = sorted(self._domain_map.keys(), key=str.lower)

        self._build_ui(source_path, source_fmt)
        self._populate_list()

    def _build_ui(self, source_path, source_fmt):
        layout = QVBoxLayout(self)

        _fmt_map = {"netscape": "Netscape / cookies.txt", "json": "JSON (Cookie-Editor)", "header": "Header String"}
        fmt_label = _fmt_map.get(source_fmt, source_fmt)

        layout.addWidget(QLabel(f"Source:  {source_path}"))
        layout.addWidget(QLabel(
            f"Format: {fmt_label}   |   "
            f"{len(self._sorted_domains)} domains   |   "
            f"{len(self._cookies)} cookies total"
        ))

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter domains:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to search…")
        self._filter_edit.textChanged.connect(self._on_filter)
        filter_row.addWidget(self._filter_edit)
        layout.addLayout(filter_row)

        btn_row = QHBoxLayout()
        for label, fn in [
            ("Select All", self._select_all),
            ("Deselect All", self._deselect_all),
            ("Invert", self._invert),
        ]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._update_sel_label)
        layout.addWidget(self._list)

        self._sel_label = QLabel("")
        layout.addWidget(self._sel_label)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Append Selected")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(btns)

    def _populate_list(self):
        self._list.blockSignals(True)
        for domain in self._sorted_domains:
            count = len(self._domain_map[domain])
            item = QListWidgetItem(
                f"{domain or '(no domain)'}  —  {count} cookie{'s' if count != 1 else ''}"
            )
            item.setData(Qt.ItemDataRole.UserRole, domain)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._update_sel_label()

    def _on_filter(self, text):
        ft = text.lower().strip()
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            domain = item.data(Qt.ItemDataRole.UserRole) or ""
            item.setHidden(bool(ft and ft not in domain.lower()))
        self._list.blockSignals(False)
        self._update_sel_label()

    def _update_sel_label(self):
        checked = self._get_checked_domains()
        cookie_count = sum(len(self._domain_map[d]) for d in checked)
        self._sel_label.setText(
            f"{len(checked)} domain(s) selected  |  {cookie_count} cookies to append"
        )
        self._ok_btn.setEnabled(len(checked) > 0)

    def _get_checked_domains(self):
        domains = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                domains.append(item.data(Qt.ItemDataRole.UserRole))
        return domains

    def _set_all(self, state):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            if not item.isHidden():
                item.setCheckState(state)
        self._list.blockSignals(False)
        self._update_sel_label()

    def _select_all(self):
        self._set_all(Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_all(Qt.CheckState.Unchecked)

    def _invert(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            if not item.isHidden():
                item.setCheckState(
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
        self._list.blockSignals(False)
        self._update_sel_label()

    def get_selected_cookies(self):
        checked = self._get_checked_domains()
        return [c for c in self._cookies if c.get("domain", "") in checked]
