from collections import defaultdict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QDialogButtonBox, QPushButton,
    QComboBox, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt

from modules.cookie_formats import save_file
from modules.utils import validate_cookies_for_format

FORMAT_KEYS = ["netscape", "json", "header"]
FORMAT_LABELS = ["Netscape / cookies.txt", "JSON (Cookie-Editor)", "Header String"]
FORMAT_EXTS = {"netscape": "*.txt", "json": "*.json", "header": "*.txt"}


class DomainExportDialog(QDialog):
    def __init__(self, cookies, default_directory="", preselected_domains=None, parent=None):
        """
        preselected_domains: set of domain strings to pre-check.
                             None means check all (default behaviour).
        """
        super().__init__(parent)
        self.setWindowTitle("Export Cookies by Domain")
        self.setMinimumSize(480, 580)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._cookies = cookies
        self._default_directory = default_directory
        self._preselected_domains = preselected_domains  # None → check all

        # Build domain → cookies mapping (sorted)
        self._domain_map = defaultdict(list)
        for c in cookies:
            self._domain_map[c.get("domain", "")].append(c)
        self._sorted_domains = sorted(self._domain_map.keys(), key=str.lower)

        self._build_ui()
        self._populate_list()   # called once — items are never recreated after this

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Summary
        total_domains = len(self._domain_map)
        total_cookies = len(self._cookies)
        self._summary = QLabel(f"{total_domains} domains  |  {total_cookies} cookies total")
        layout.addWidget(self._summary)

        # Filter-origin notice
        if self._preselected_domains is not None:
            n = len(self._preselected_domains)
            notice = QLabel(
                f"⚑  Pre-selected {n} domain(s) from the active main-window filter. "
                "Unchecked domains are still shown — tick them to include."
            )
            notice.setWordWrap(True)
            notice.setStyleSheet("color: #0057b8; font-style: italic;")
            layout.addWidget(notice)

        # Domain filter
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter domains:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to search…")
        self._filter_edit.textChanged.connect(self._on_filter)
        filter_row.addWidget(self._filter_edit)
        layout.addLayout(filter_row)

        # Select buttons
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

        # Domain list
        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list)

        # Selection summary
        self._sel_label = QLabel("")
        layout.addWidget(self._sel_label)

        # Format selector
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Export format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(FORMAT_LABELS)
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Buttons
        btn_box = QDialogButtonBox()
        self._export_btn = QPushButton("Export…")
        self._export_btn.setDefault(True)
        close_btn = QPushButton("Close")
        btn_box.addButton(self._export_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton(close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        self._export_btn.clicked.connect(self._do_export)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(btn_box)

    def _populate_list(self):
        """Create all items once. Filter shows/hides them without resetting state."""
        self._list.blockSignals(True)
        for domain in self._sorted_domains:
            count = len(self._domain_map[domain])
            item = QListWidgetItem(
                f"{domain or '(no domain)'}  —  {count} cookie{'s' if count != 1 else ''}"
            )
            item.setData(Qt.ItemDataRole.UserRole, domain)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if self._preselected_domains is None:
                checked = Qt.CheckState.Checked
            else:
                checked = (Qt.CheckState.Checked if domain in self._preselected_domains
                           else Qt.CheckState.Unchecked)
            item.setCheckState(checked)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._update_sel_label()

    def _on_filter(self, text):
        """Show/hide items — never recreate them so checkbox state is preserved."""
        ft = text.lower().strip()
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            domain = item.data(Qt.ItemDataRole.UserRole) or ""
            item.setHidden(bool(ft and ft not in domain.lower()))
        self._list.blockSignals(False)
        self._update_sel_label()

    def _on_item_changed(self, _item):
        self._update_sel_label()

    def _update_sel_label(self):
        # Count ALL checked items, including those hidden by the filter
        checked_domains = self._get_checked_domains(visible_only=False)
        cookie_count = sum(len(self._domain_map[d]) for d in checked_domains)
        self._sel_label.setText(
            f"{len(checked_domains)} domain(s) selected  |  {cookie_count} cookies to export"
        )
        self._export_btn.setEnabled(len(checked_domains) > 0)

    def _get_checked_domains(self, visible_only=False):
        domains = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if visible_only and item.isHidden():
                continue
            if item.checkState() == Qt.CheckState.Checked:
                domains.append(item.data(Qt.ItemDataRole.UserRole))
        return domains

    def _set_all(self, state):
        """Apply state only to currently visible rows."""
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
        """Invert only visible rows."""
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

    def _do_export(self):
        checked_domains = self._get_checked_domains()
        if not checked_domains:
            QMessageBox.information(self, "Nothing Selected", "Select at least one domain to export.")
            return

        selected_cookies = [
            c for c in self._cookies
            if c.get("domain", "") in checked_domains
        ]

        fmt_idx = self._fmt_combo.currentIndex()
        fmt = FORMAT_KEYS[fmt_idx]
        fmt_label = FORMAT_LABELS[fmt_idx]
        ext = FORMAT_EXTS[fmt]

        errors = validate_cookies_for_format(selected_cookies, fmt)
        if errors:
            msg = "Validation errors:\n\n" + "\n".join(errors[:20])
            if len(errors) > 20:
                msg += f"\n… and {len(errors) - 20} more"
            r = QMessageBox.warning(
                self, "Validation Errors", msg + "\n\nExport anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        filters = f"{fmt_label} ({ext});;All Files (*)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Cookies", self._default_directory, filters
        )
        if not path:
            return

        try:
            save_file(path, {"cookies": selected_cookies, "comments": []}, fmt)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save:\n{e}")
            return

        QMessageBox.information(
            self, "Export Complete",
            f"Exported {len(selected_cookies)} cookies from {len(checked_domains)} domain(s) to:\n{path}",
        )
