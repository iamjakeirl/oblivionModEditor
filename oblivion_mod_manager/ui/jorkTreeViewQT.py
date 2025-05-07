from PyQt5.QtCore import Qt, QAbstractItemModel, QModelIndex, QVariant
from PyQt5.QtGui  import QColor
from mod_manager.utils import get_display_info

class _Node:
    def __init__(self, data: dict | str, parent=None, is_group=False):
        self.parent   = parent
        self.children = []
        self.data     = data   # dict(row) for leaves, str(group name) for branches
        self.is_group = is_group

    def child(self, row):        return self.children[row]
    def child_count(self):       return len(self.children)
    def row(self):               return self.parent.children.index(self) if self.parent else 0

class ModTreeModel(QAbstractItemModel):
    COLS = ["Display\u00A0Name"]      # Only one column now

    def __init__(self, rows, *, show_real_cb, colors=None, parent=None):
        super().__init__(parent)
        self.colors      = colors or {
            'bg':  QColor('#181818'),
            'fg':  QColor('#e0e0e0'),
            'selbg': QColor('#333333'),
            'selfg': QColor('#ff9800'),
        }
        self.show_real   = show_real_cb
        self.root        = _Node("ROOT")
        self._build_tree(rows)

    # ------------- public helpers -------------
    def index(self, row, col, parent=QModelIndex()):
        node = parent.internalPointer() if parent.isValid() else self.root
        return self.createIndex(row, col, node.child(row))

    def parent(self, index):
        if not index.isValid(): return QModelIndex()
        node = index.internalPointer()
        if node.parent == self.root: return QModelIndex()
        return self.createIndex(node.parent.row(), 0, node.parent)

    def rowCount(self, parent=QModelIndex()):
        node = parent.internalPointer() if parent.isValid() else self.root
        return node.child_count()

    def columnCount(self, parent=QModelIndex()):  return 1

    def headerData(self, col, orient, role):
        if orient == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLS[col]
        return QVariant()

    def data(self, index, role):
        if not index.isValid(): return QVariant()
        node  = index.internalPointer()
        col   = index.column()

        if role == Qt.ForegroundRole:  return self.colors['fg']
        if role == Qt.BackgroundRole:  return self.colors['bg']
        if role == Qt.TextAlignmentRole: return Qt.AlignLeft | Qt.AlignVCenter

        # display text
        if role in (Qt.DisplayRole, Qt.EditRole):
            if node.is_group:
                return node.data if col == 0 else ""
            row = node.data                          # leaf: our original row dict
            disp = get_display_info(row["id"])
            if not disp.get("display") and not disp.get("group"):
                # Try normalized id (strip DisabledMods prefix)
                import re
                subfolder, name = row["id"].split("|", 1)
                norm_subfolder = re.sub(r'^(DisabledMods[\\/]+)', '', subfolder, flags=re.IGNORECASE)
                norm_id = f"{norm_subfolder}|{name}"
                disp = get_display_info(norm_id)
                if not disp.get("display") and not disp.get("group"):
                    # Try just |name
                    disp = get_display_info(f"|{name}")
            if col == 0:
                txt = disp.get("display", row["real"])
                if self.show_real(): txt = row["real"]
                return txt
        return QVariant()

    def flags(self, index):
        node = index.internalPointer()
        if node.is_group:                            # group headers not editable/selectable
            return Qt.ItemIsEnabled
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() == 0:
            base |= Qt.ItemIsEditable
        return base

    # ------------- private helpers -------------
    def _build_tree(self, rows):
        groups = {}
        for r in rows:
            # Fallback logic for group lookup
            disp = get_display_info(r["id"])
            if not disp.get("group"):
                import re
                subfolder, name = r["id"].split("|", 1)
                norm_subfolder = re.sub(r'^(DisabledMods[\\/]+)', '', subfolder, flags=re.IGNORECASE)
                norm_id = f"{norm_subfolder}|{name}"
                disp = get_display_info(norm_id)
                if not disp.get("group"):
                    disp = get_display_info(f"|{name}")
            grp_chain = (disp.get("group", "") or "Ungrouped").split("/")
            parent = self.root
            path   = []
            for g in grp_chain:
                path.append(g)
                key = "/".join(path)
                if key not in groups:
                    node = _Node(g, parent, is_group=True)
                    parent.children.append(node)
                    groups[key] = node
                parent = groups[key]
            parent.children.append(_Node(r, parent, is_group=False)) 