from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PyQt6.QtGui import QColor

COLUMNS = ["domain", "flag", "path", "secure", "expiry", "name", "value"]
HEADERS = ["Domain", "Flag", "Path", "Secure", "Expiry", "Name", "Value"]
EXPIRY_COL = COLUMNS.index("expiry")


class CookieTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cookies = []
        self._modified = set()

    def load(self, cookies):
        self.beginResetModel()
        self._cookies = list(cookies)
        self._modified.clear()
        self.endResetModel()

    def all_cookies(self):
        return self._cookies

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._cookies)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._cookies):
            return None

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._cookies[row].get(COLUMNS[col], "")

        if role == Qt.ItemDataRole.BackgroundRole and row in self._modified:
            return QColor(255, 255, 200)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(HEADERS):
                return HEADERS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def add_cookie(self, cookie):
        row = len(self._cookies)
        self.beginInsertRows(QModelIndex(), row, row)
        self._cookies.append(cookie)
        self._modified.add(row)
        self.endInsertRows()

    def update_cookie(self, row, cookie):
        if 0 <= row < len(self._cookies):
            self._cookies[row] = cookie
            self._modified.add(row)
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, len(COLUMNS) - 1),
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole],
            )

    def remove_by_source_rows(self, rows):
        self.beginResetModel()
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._cookies):
                del self._cookies[row]
        self._modified.clear()
        self.endResetModel()

    def clear_modified(self):
        self._modified.clear()
        if self._cookies:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._cookies) - 1, len(COLUMNS) - 1),
                [Qt.ItemDataRole.BackgroundRole],
            )


class CookieFilterProxyModel(QSortFilterProxyModel):
    # scope constants
    SCOPE_BOTH   = "both"
    SCOPE_DOMAIN = "domain"
    SCOPE_NAME   = "name"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._terms = []        # list of lowercase strings (OR logic)
        self._scope = self.SCOPE_BOTH

    def set_filter(self, text, scope=None):
        if scope is not None:
            self._scope = scope
        self._terms = [t.strip().lower() for t in text.split(",") if t.strip()]
        self.invalidateFilter()

    def set_scope(self, scope):
        self._scope = scope
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._terms:
            return True
        model = self.sourceModel()

        candidates = []
        if self._scope in (self.SCOPE_BOTH, self.SCOPE_DOMAIN):
            candidates.append(
                (model.data(model.index(source_row, COLUMNS.index("domain"))) or "").lower()
            )
        if self._scope in (self.SCOPE_BOTH, self.SCOPE_NAME):
            candidates.append(
                (model.data(model.index(source_row, COLUMNS.index("name"))) or "").lower()
            )

        # Row accepted if ANY term matches ANY candidate field
        return any(term in candidate for term in self._terms for candidate in candidates)

    def lessThan(self, left, right):
        col = left.column()
        lv = self.sourceModel().data(left) or ""
        rv = self.sourceModel().data(right) or ""

        # Numeric sort for expiry column
        if col == EXPIRY_COL:
            try:
                return int(lv) < int(rv)
            except (ValueError, TypeError):
                pass

        return lv.lower() < rv.lower()
