from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant
from mod_manager.utils import get_display_info, set_display_info
from PyQt5.QtGui import QColor

COLUMN_HEADERS = ["Display Name", "Sub‑folder", "Group"]

class ModTableModel(QAbstractTableModel):
    def __init__(self, rows, get_show_real=None, get_hide_folder=None, parent=None, colors=None):
        super().__init__(parent)
        self._rows = rows          # list of dicts from pak_manager / registry
        self.get_show_real = get_show_real or (lambda: False)
        self.get_hide_folder = get_hide_folder or (lambda: False)
        # Color scheme
        self.colors = colors or {
            'background': QColor('#181818'),
            'foreground': QColor('#e0e0e0'),
            'selection_background': QColor('#333333'),
            'selection_foreground': QColor('#ff9800'),
        }

    # ---------- Qt overrides ----------
    def rowCount(self, parent=QModelIndex()):    return len(self._rows)
    def columnCount(self, parent=QModelIndex()): return 3
    def headerData(self, col, orient, role):
        if orient == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMN_HEADERS[col]
        return QVariant()

    def data(self, index, role):
        r, c = index.row(), index.column()
        row = self._rows[r]
        mod_id = row["id"]
        disp = get_display_info(mod_id)
        if role == Qt.BackgroundRole:
            return self.colors.get('background', QVariant())
        if role == Qt.ForegroundRole:
            return self.colors.get('foreground', QVariant())
        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter
        if role == Qt.DisplayRole or role == Qt.EditRole:
            if c == 0:  # display
                name = disp.get("display", row["real"])
                if self.get_show_real():
                    name = row["real"]
                # Always just show the name, never the folder structure
                return name
            elif c == 1:  # subfolder
                return row.get("subfolder") or ""
            elif c == 2:  # group
                return disp.get("group", "")
        return QVariant()

    def flags(self, index):
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() in (0, 3):   # editable cols
            base |= Qt.ItemIsEditable
        return base

    def setData(self, index, value, role):
        if role != Qt.EditRole: return False
        r, c = index.row(), index.column()
        mod_id = self._rows[r]["id"]
        if c == 0:
            set_display_info(mod_id, display=value.strip())
        elif c == 3:
            set_display_info(mod_id, group=value.strip())
        else:
            return False
        self.dataChanged.emit(index, index, [Qt.DisplayRole])
        return True 