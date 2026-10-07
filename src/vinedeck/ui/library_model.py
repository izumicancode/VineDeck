"""Qt list model over the (already filtered and sorted) applications."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, Qt, Signal

from ..database.models import Application
from .formatting import format_last_played

AppRole = Qt.UserRole + 1
StateRole = Qt.UserRole + 2
IdRole = Qt.UserRole + 3
MIME = "application/x-vinedeck-app-id"


class LibraryModel(QAbstractListModel):
    reorder_requested = Signal(int, int)        # dragged id, target id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps: list[Application] = []
        self._states: dict[int, str] = {}

    # -- data ------------------------------------------------------------------
    def set_applications(self, apps: list[Application]) -> None:
        self.beginResetModel()
        self._apps = list(apps)
        self.endResetModel()

    def set_state(self, app_id: int, state: str | None) -> None:
        if state is None:
            self._states.pop(app_id, None)
        else:
            self._states[app_id] = state
        row = self.row_of(app_id)
        if row >= 0:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [StateRole])

    def state(self, app_id: int) -> str | None:
        return self._states.get(app_id)

    def row_of(self, app_id: int) -> int:
        for i, a in enumerate(self._apps):
            if a.id == app_id:
                return i
        return -1

    def app_at(self, row: int) -> Application | None:
        return self._apps[row] if 0 <= row < len(self._apps) else None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._apps)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._apps):
            return None
        app = self._apps[index.row()]
        if role == Qt.DisplayRole:
            return app.name
        if role == AppRole:
            return app
        if role == IdRole:
            return app.id
        if role == StateRole:
            return self._states.get(app.id)
        if role == Qt.AccessibleTextRole:
            bits = [app.name, app.category_name or "Uncategorised",
                    f"Last played: {format_last_played(app.last_played)}"]
            if app.favorite:
                bits.append("favorite")
            if self._states.get(app.id):
                bits.append(self._states[app.id])
            return ", ".join(bits)
        return None

    # -- drag & drop reordering ----------------------------------------------------
    def flags(self, index):
        base = super().flags(index)
        if index.isValid():
            return base | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        return base | Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        return Qt.CopyAction

    def mimeTypes(self):
        return [MIME]

    def mimeData(self, indexes):
        data = QMimeData()
        for idx in indexes:
            if idx.isValid():
                data.setData(MIME, str(self._apps[idx.row()].id).encode())
                break
        return data

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasFormat(MIME)

    def dropMimeData(self, data, action, row, column, parent):
        if not data.hasFormat(MIME):
            return False
        try:
            dragged = int(bytes(data.data(MIME)).decode())
        except ValueError:
            return False
        if parent.isValid():
            target_row = parent.row()
        elif row >= 0:
            target_row = min(row, len(self._apps) - 1)
        else:
            return False
        target = self.app_at(target_row)
        if target is None or target.id == dragged:
            return False
        self.reorder_requested.emit(dragged, target.id)
        return True
