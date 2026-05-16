import sys
import os
import ctypes

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableView, QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QLineEdit, QLabel, QComboBox, QDialog, QHeaderView,
    QAbstractItemView, QPushButton, QMenu, QListWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QIcon

from modules.cookie_model import CookieTableModel, CookieFilterProxyModel
from modules.cookie_formats import detect_format, parse_file_as, save_file
from modules.edit_dialog import CookieEditDialog
from modules.browser_import import BrowserImportDialog
from modules.domain_export import DomainExportDialog
from modules.append_dialog import DomainImportDialog
from modules.filter_dialog import FilterEditDialog, SCOPE_KEYS as FILTER_SCOPE_KEYS
from modules.utils import load_config, save_config, validate_cookies_for_format

FORMAT_KEYS = ["netscape", "json", "header"]
FORMAT_LABELS = ["Netscape / cookies.txt", "JSON (Cookie-Editor)", "Header String"]
FORMAT_EXTS = {"netscape": "*.txt", "json": "*.json", "header": "*.txt"}
OPEN_FILTER = "Cookie Files (*.txt *.json);;All Files (*)"

SCOPE_OPTIONS = [
    CookieFilterProxyModel.SCOPE_BOTH,
    CookieFilterProxyModel.SCOPE_DOMAIN,
    CookieFilterProxyModel.SCOPE_NAME,
]

# Quick filter presets: (label, search_text, scope)
QUICK_FILTERS = [
    (
        "Auth / Login cookies",
        "session, token, auth, login, sid, ssid, jwt, oauth, userid, "
        "user_id, credential, apikey, api_key, access_key, refresh, bearer",
        CookieFilterProxyModel.SCOPE_NAME,
    ),
    (
        "YouTube / Google  (yt-dlp)",
        "youtube.com, google.com, googlevideo.com, ggpht.com",
        CookieFilterProxyModel.SCOPE_DOMAIN,
    ),
    (
        "Clear filter",
        "",
        CookieFilterProxyModel.SCOPE_BOTH,
    ),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._config = load_config()
        self._current_file = None
        self._current_format = None
        self._comments = []
        self._unsaved = False

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._persist_config)

        self._build_ui()
        self._build_menus()
        self._setup_table()
        self._update_title()
        self._update_status()

        # Restore window geometry
        w = self._config.get("window", {})
        self.resize(w.get("width", 1200), w.get("height", 700))
        x, y = w.get("x"), w.get("y")
        if x is not None and y is not None:
            self.move(x, y)

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Filter / format bar
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Search:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter — comma-separated for OR  e.g. session, token, sid")
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        bar.addWidget(self._filter_edit, 1)

        self._scope_combo = QComboBox()
        self._scope_combo.addItems(["Domain + Name", "Domain only", "Name only"])
        self._scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        bar.addWidget(self._scope_combo)

        self._presets_btn = QPushButton("Quick Filter ▾")
        self._presets_btn.setToolTip("Apply a preset search pattern")
        self._presets_btn.clicked.connect(self._show_presets_menu)
        bar.addWidget(self._presets_btn)

        bar.addWidget(QLabel("Format:"))
        self._format_combo = QComboBox()
        self._format_combo.addItems(FORMAT_LABELS)
        self._format_combo.setEnabled(False)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        bar.addWidget(self._format_combo)
        root.addLayout(bar)

        # Table
        self._table = QTableView()
        root.addWidget(self._table)

        # Status bar
        self._status_label = QLabel("No file loaded")
        sb = QStatusBar()
        sb.addWidget(self._status_label)
        self.setStatusBar(sb)

    def _build_menus(self):
        mb = self.menuBar()

        # File
        fm = mb.addMenu("File")
        self._add_action(fm, "Open…", self._open_file, QKeySequence.StandardKey.Open)
        self._add_action(fm, "Append from File…", self._append_from_file, QKeySequence("Ctrl+Shift+A"))
        self._add_action(fm, "Save", self._save_file, QKeySequence.StandardKey.Save)
        self._add_action(fm, "Save As…", self._save_as, QKeySequence("Ctrl+Shift+S"))
        fm.addSeparator()
        self._add_action(fm, "Quit", self.close, QKeySequence.StandardKey.Quit)

        # Edit
        em = mb.addMenu("Edit")
        self._add_action(em, "Add Cookie", self._add_cookie, QKeySequence("Ctrl+Ins"))
        self._add_action(em, "Edit Cookie", self._edit_selected, QKeySequence("Return"))
        self._add_action(em, "Delete Selected", self._delete_selected, QKeySequence.StandardKey.Delete)

        # Import
        im = mb.addMenu("Import")
        self._add_action(im, "From Browser…", self._import_from_browser)

        # Export
        ex = mb.addMenu("Export")
        self._add_action(ex, "Export by Domain…", self._export_by_domain, QKeySequence("Ctrl+E"))

        # Toolbar
        tb = QToolBar("Main")
        self.addToolBar(tb)
        tb.setMovable(False)
        for label, fn in [
            ("Open", self._open_file),
            ("Append", self._append_from_file),
            ("Save", self._save_file),
            (None, None),
            ("Add", self._add_cookie),
            ("Edit", self._edit_selected),
            ("Delete", self._delete_selected),
            (None, None),
            ("Import Browser", self._import_from_browser),
            (None, None),
            ("Export by Domain", self._export_by_domain),
        ]:
            if label is None:
                tb.addSeparator()
            else:
                act = QAction(label, self)
                act.triggered.connect(fn)
                tb.addAction(act)

    @staticmethod
    def _add_action(menu, label, fn, shortcut=None):
        act = QAction(label, menu.parent())
        act.triggered.connect(fn)
        if shortcut:
            act.setShortcut(shortcut)
        menu.addAction(act)
        return act

    # -------------------------------------------------------------- Table --

    def _setup_table(self):
        self._source_model = CookieTableModel()
        self._proxy = CookieFilterProxyModel()
        self._proxy.setSourceModel(self._source_model)

        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)  # enabled after data load

        header = self._table.horizontalHeader()
        for i in range(self._source_model.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)

        self._table.doubleClicked.connect(self._edit_at_proxy_index)

        header.sectionResized.connect(self._schedule_config_save)
        header.sectionMoved.connect(self._schedule_config_save)
        header.sortIndicatorChanged.connect(self._schedule_config_save)

    def _apply_column_visibility(self, fmt):
        """Show all columns for netscape/json; hide metadata columns for header format."""
        from modules.cookie_model import COLUMNS
        header_hidden = {"domain", "flag", "path", "secure", "expiry"}
        for i, col in enumerate(COLUMNS):
            hide = (fmt == "header") and (col in header_hidden)
            self._table.setColumnHidden(i, hide)

    def _populate_and_restore(self):
        """Call after loading cookies: enable sorting, then restore state."""
        self._table.setSortingEnabled(True)
        self._restore_table_state()

    def _restore_table_state(self):
        header = self._table.horizontalHeader()
        header.blockSignals(True)

        widths = self._config.get("column_widths", [])
        for i, w in enumerate(widths):
            if i < self._source_model.columnCount() and w > 0:
                self._table.setColumnWidth(i, w)

        order = self._config.get("column_order", [])
        for visual, logical in enumerate(order):
            current = header.visualIndex(logical)
            if current != visual:
                header.moveSection(current, visual)

        sort_col = self._config.get("sort_column", -1)
        sort_order = self._config.get("sort_order", 0)
        if sort_col >= 0:
            self._table.sortByColumn(sort_col, Qt.SortOrder(sort_order))

        header.blockSignals(False)

    def _save_table_state(self):
        header = self._table.horizontalHeader()
        col_count = self._source_model.columnCount()
        # Preserve previously-saved widths for hidden columns (they report 0 when hidden)
        saved = self._config.get("column_widths", [0] * col_count)
        while len(saved) < col_count:
            saved.append(0)
        widths = [
            (saved[i] if self._table.isColumnHidden(i) else self._table.columnWidth(i))
            for i in range(col_count)
        ]
        self._config["column_widths"] = widths
        self._config["column_order"] = [header.logicalIndex(i) for i in range(col_count)]
        self._config["sort_column"] = header.sortIndicatorSection()
        self._config["sort_order"] = header.sortIndicatorOrder().value

    # ----------------------------------------------------------- Config --

    def _schedule_config_save(self, *_):
        self._save_timer.start(500)

    def _persist_config(self):
        self._save_table_state()
        g = self.geometry()
        self._config["window"] = {"width": g.width(), "height": g.height(), "x": g.x(), "y": g.y()}
        save_config(self._config)

    # --------------------------------------------------------- Title / status --

    def _update_title(self):
        name = os.path.basename(self._current_file) if self._current_file else "Untitled"
        marker = " *" if self._unsaved else ""
        self.setWindowTitle(f"Cookie Editor — {name}{marker}")

    def _update_status(self):
        if self._current_file:
            fmt_label = FORMAT_LABELS[FORMAT_KEYS.index(self._current_format)] if self._current_format else "?"
            visible = self._proxy.rowCount()
            total = len(self._source_model.all_cookies())
            shown = f"{visible}/{total}" if visible != total else str(total)
            parts = [self._current_file, f"Format: {fmt_label}", f"{shown} cookies"]
            if self._current_format == "header":
                parts.append("Header format: only Name and Value are stored — Domain/Path/Expiry are not available in this format")
            self._status_label.setText("   |   ".join(parts))
        else:
            total = len(self._source_model.all_cookies())
            if total:
                self._status_label.setText(f"Unsaved import — {total} cookies (not saved)")
            else:
                self._status_label.setText("No file loaded")

    def _set_unsaved(self, value=True):
        self._unsaved = value
        self._update_title()

    # ----------------------------------------------------------- File ops --

    def _confirm_discard(self):
        if not self._unsaved:
            return True
        r = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Discard and continue?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return r == QMessageBox.StandardButton.Discard

    def _open_file(self):
        if not self._confirm_discard():
            return
        default = self._config.get("default_directory") or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Open Cookie File", default, OPEN_FILTER)
        if not path:
            return
        self._config["default_directory"] = os.path.dirname(path)
        self._load_file(path)

    def _load_file(self, path, fmt=None):
        try:
            fmt = fmt or detect_format(path)
            data = parse_file_as(path, fmt)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Could not load file:\n{e}")
            return

        self._current_file = path
        self._current_format = fmt
        self._comments = data.get("comments", [])
        self._config["last_opened_file"] = path

        # Always clear the filter on file open so no rows are hidden accidentally
        self._filter_edit.blockSignals(True)
        self._filter_edit.clear()
        self._filter_edit.blockSignals(False)
        self._scope_combo.blockSignals(True)
        self._scope_combo.setCurrentIndex(0)
        self._scope_combo.blockSignals(False)
        self._proxy.set_filter("", scope=CookieFilterProxyModel.SCOPE_BOTH)

        self._source_model.load(data.get("cookies", []))
        self._apply_column_visibility(fmt)
        self._populate_and_restore()

        self._format_combo.blockSignals(True)
        self._format_combo.setCurrentIndex(FORMAT_KEYS.index(fmt))
        self._format_combo.setEnabled(True)
        self._format_combo.blockSignals(False)

        self._set_unsaved(False)
        self._update_status()
        self._persist_config()

    def _append_from_file(self):
        default = self._config.get("default_directory") or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Append Cookies from File", default, OPEN_FILTER)
        if not path:
            return

        try:
            fmt = detect_format(path)
            data = parse_file_as(path, fmt)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Could not read file:\n{e}")
            return

        source_cookies = data.get("cookies", [])
        if not source_cookies:
            QMessageBox.information(self, "Empty File", "No cookies found in the selected file.")
            return

        dlg = DomainImportDialog(source_cookies, path, fmt, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        to_append = dlg.get_selected_cookies()
        if not to_append:
            return

        for cookie in to_append:
            self._source_model.add_cookie(cookie)

        self._set_unsaved(True)
        self._update_status()
        QMessageBox.information(
            self, "Appended",
            f"Appended {len(to_append)} cookie(s) from {len(set(c.get('domain','') for c in to_append))} domain(s).",
        )

    def _on_format_changed(self, idx):
        new_fmt = FORMAT_KEYS[idx]
        if new_fmt != self._current_format:
            self._current_format = new_fmt
            self._set_unsaved(True)
            self._update_status()

    def _on_filter_changed(self, text):
        self._proxy.set_filter(text)
        self._update_status()

    def _on_scope_changed(self, idx):
        self._proxy.set_scope(SCOPE_OPTIONS[idx])
        self._update_status()

    def _show_presets_menu(self):
        menu = QMenu(self)

        # Built-in presets
        for label, text, scope in QUICK_FILTERS:
            act = menu.addAction(label)
            act.setData(("apply", text, scope))

        # Saved filters
        saved = self._config.get("saved_filters", [])
        if saved:
            menu.addSeparator()
            for f in saved:
                scope_label = {"both": "Domain+Name", "domain": "Domain", "name": "Name"}.get(
                    f["scope"], f["scope"]
                )
                act = menu.addAction(f"★  {f['name']}  [{scope_label}]")
                act.setData(("apply", f["text"], f["scope"]))

        menu.addSeparator()
        menu.addAction("New saved filter…").setData(("new", None, None))
        menu.addAction("Manage saved filters…").setData(("manage", None, None))

        chosen = menu.exec(self._presets_btn.mapToGlobal(
            self._presets_btn.rect().bottomLeft()
        ))
        if not chosen:
            return

        action, text, scope = chosen.data()
        if action == "apply":
            self._scope_combo.setCurrentIndex(SCOPE_OPTIONS.index(scope))
            self._filter_edit.setText(text)
        elif action == "new":
            self._new_saved_filter()
        elif action == "manage":
            self._manage_saved_filters()

    def _new_saved_filter(self):
        dlg = FilterEditDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        f = dlg.get_filter()
        saved = self._config.get("saved_filters", [])
        for existing in saved:
            if existing["name"] == f["name"]:
                existing["text"] = f["text"]
                existing["scope"] = f["scope"]
                self._persist_config()
                return
        saved.append(f)
        self._config["saved_filters"] = saved
        self._persist_config()

    def _manage_saved_filters(self):
        saved = self._config.get("saved_filters", [])

        dlg = QDialog(self)
        dlg.setWindowTitle("Manage Saved Filters")
        dlg.setMinimumSize(520, 340)
        layout = QVBoxLayout(dlg)

        lst = QListWidget()

        def _refresh_list():
            lst.clear()
            for f in saved:
                scope_label = {"both": "Domain+Name", "domain": "Domain", "name": "Name"}.get(
                    f["scope"], f["scope"]
                )
                lst.addItem(f"{f['name']}  [{scope_label}]  —  {f['text'][:60]}")

        _refresh_list()
        layout.addWidget(lst)

        btn_row = QHBoxLayout()
        new_btn  = QPushButton("New Filter")
        edit_btn = QPushButton("Edit Selected")
        del_btn  = QPushButton("Delete Selected")
        close_btn = QPushButton("Close")
        for b in (new_btn, edit_btn, del_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        def _new():
            d = FilterEditDialog(parent=dlg)
            if d.exec() != QDialog.DialogCode.Accepted:
                return
            f = d.get_filter()
            for existing in saved:
                if existing["name"] == f["name"]:
                    existing.update(f)
                    _refresh_list()
                    self._persist_config()
                    return
            saved.append(f)
            self._config["saved_filters"] = saved
            _refresh_list()
            self._persist_config()

        def _edit():
            row = lst.currentRow()
            if row < 0:
                return
            d = FilterEditDialog(filter_data=saved[row], parent=dlg)
            if d.exec() != QDialog.DialogCode.Accepted:
                return
            saved[row] = d.get_filter()
            self._config["saved_filters"] = saved
            _refresh_list()
            self._persist_config()

        def _delete():
            row = lst.currentRow()
            if row < 0:
                return
            saved.pop(row)
            self._config["saved_filters"] = saved
            _refresh_list()
            self._persist_config()

        new_btn.clicked.connect(_new)
        edit_btn.clicked.connect(_edit)
        del_btn.clicked.connect(_delete)
        close_btn.clicked.connect(dlg.accept)
        dlg.exec()

    def _save_file(self):
        if not self._current_file:
            self._save_as()
            return
        self._do_save(self._current_file, self._current_format)

    def _save_as(self):
        filters = ";;".join(
            f"{FORMAT_LABELS[i]} ({FORMAT_EXTS[FORMAT_KEYS[i]]})" for i in range(len(FORMAT_KEYS))
        ) + ";;All Files (*)"
        default = self._config.get("default_directory") or os.path.expanduser("~")
        path, selected = QFileDialog.getSaveFileName(self, "Save As", default, filters)
        if not path:
            return

        fmt = self._current_format or "netscape"
        for i, label in enumerate(FORMAT_LABELS):
            if label in selected:
                fmt = FORMAT_KEYS[i]
                break

        self._config["default_directory"] = os.path.dirname(path)
        self._current_file = path
        self._current_format = fmt

        self._format_combo.blockSignals(True)
        self._format_combo.setCurrentIndex(FORMAT_KEYS.index(fmt))
        self._format_combo.setEnabled(True)
        self._format_combo.blockSignals(False)

        self._do_save(path, fmt)

    def _do_save(self, path, fmt):
        cookies = self._source_model.all_cookies()

        # Warn about data loss when saving as header string
        if fmt == "header" and self._current_format != "header":
            r = QMessageBox.warning(
                self, "Data Loss Warning",
                "Header String format only stores cookie Name and Value.\n\n"
                "Domain, Path, Expiry, Secure and Flag will NOT be saved.\n"
                "If you open this file again, those columns will be empty.\n\n"
                "Save as Header String anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        errors = validate_cookies_for_format(cookies, fmt)
        if errors:
            msg = "Validation errors:\n\n" + "\n".join(errors[:20])
            if len(errors) > 20:
                msg += f"\n… and {len(errors) - 20} more"
            r = QMessageBox.warning(
                self, "Validation Errors", msg + "\n\nSave anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        try:
            save_file(path, {"cookies": cookies, "comments": self._comments}, fmt)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save:\n{e}")
            return

        self._source_model.clear_modified()
        self._config["last_opened_file"] = path
        self._set_unsaved(False)
        self._update_status()
        self._persist_config()

    # --------------------------------------------------------- Edit ops --

    def _add_cookie(self):
        dlg = CookieEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._source_model.add_cookie(dlg.get_cookie())
            self._set_unsaved(True)
            self._update_status()

    def _edit_selected(self):
        rows = self._table.selectionModel().selectedRows()
        if rows:
            self._edit_at_proxy_index(rows[0])

    def _edit_at_proxy_index(self, proxy_index):
        src_index = self._proxy.mapToSource(proxy_index)
        src_row = src_index.row()
        cookie = self._source_model.all_cookies()[src_row]
        dlg = CookieEditDialog(cookie=dict(cookie), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = {**cookie, **dlg.get_cookie()}  # preserve extra JSON meta fields
            self._source_model.update_cookie(src_row, updated)
            self._set_unsaved(True)

    def _delete_selected(self):
        proxy_rows = self._table.selectionModel().selectedRows()
        if not proxy_rows:
            return
        src_rows = sorted(
            {self._proxy.mapToSource(i).row() for i in proxy_rows}
        )
        r = QMessageBox.question(
            self, "Delete Cookies",
            f"Delete {len(src_rows)} selected cookie(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            self._source_model.remove_by_source_rows(src_rows)
            self._set_unsaved(True)
            self._update_status()

    # --------------------------------------------------- Browser import --

    def _import_from_browser(self):
        dlg = BrowserImportDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        imported = dlg.get_cookies()
        if not imported:
            return

        existing = self._source_model.all_cookies()
        if existing:
            r = QMessageBox.question(
                self, "Import Cookies",
                f"Current table has {len(existing)} cookies.\n"
                f"Replace with {len(imported)} imported, or append?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.No:
                imported = existing + imported  # append

        self._current_file = None
        self._current_format = "netscape"
        self._comments = []
        self._source_model.load(imported)
        self._apply_column_visibility("netscape")
        self._populate_and_restore()

        self._format_combo.blockSignals(True)
        self._format_combo.setCurrentIndex(FORMAT_KEYS.index("netscape"))
        self._format_combo.setEnabled(True)
        self._format_combo.blockSignals(False)

        self._set_unsaved(True)
        self._update_status()

    # -------------------------------------------------- Domain export --

    def _export_by_domain(self):
        all_cookies = self._source_model.all_cookies()
        if not all_cookies:
            QMessageBox.information(self, "No Data", "No cookies loaded to export.")
            return

        # Pre-select only the domains visible under the current filter
        visible = self._proxy.rowCount()
        if 0 < visible < len(all_cookies):
            preselected = set()
            for i in range(visible):
                src = self._proxy.mapToSource(self._proxy.index(i, 0))
                preselected.add(all_cookies[src.row()].get("domain", ""))
        else:
            preselected = None  # no filter active → check all

        default = self._config.get("default_directory") or os.path.expanduser("~")
        dlg = DomainExportDialog(
            all_cookies, default_directory=default,
            preselected_domains=preselected, parent=self,
        )
        dlg.exec()

    # -------------------------------------------------------------- Close --

    def closeEvent(self, event):
        if self._unsaved:
            r = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Quit without saving?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if r != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self._persist_config()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_config_save()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_config_save()


def _set_taskbar_icon_windows(window, icon_path):
    """On Windows, setWindowIcon() alone does not update the taskbar.
    SendMessageW(WM_SETICON) with a handle from LoadImageW is required.
    LoadImageW.restype must be c_void_p to prevent 32-bit handle truncation on 64-bit."""
    try:
        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        hicon = user32.LoadImageW(
            None,
            icon_path,
            1,       # IMAGE_ICON
            0, 0,
            0x10 | 0x40,  # LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        if hicon:
            WM_SETICON = 0x0080
            ICON_SMALL, ICON_BIG = 0, 1
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
    except Exception:
        pass  # non-fatal: icon simply won't appear in taskbar


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Cookie Editor")

    icon_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "config", "assets", "cookie_edit.png",
    )
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    if sys.platform == "win32" and os.path.isfile(icon_path):
        _set_taskbar_icon_windows(window, icon_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
