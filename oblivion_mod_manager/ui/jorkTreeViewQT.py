from PyQt5.QtCore import Qt, QAbstractItemModel, QModelIndex, QVariant, QMimeData, QTimer, QCoreApplication
from PyQt5.QtGui  import QColor
from mod_manager.utils import get_display_info, set_display_info
import traceback

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
    MIME = "obmm/mod-ids"

    def __init__(self, rows, *, show_real_cb=None, colors=None, parent=None):
        super().__init__(parent)
        self.colors = colors or {
            'bg':  QColor('#181818'),
            'fg':  QColor('#e0e0e0'),
            'selbg': QColor('#333333'),
            'selfg': QColor('#ff9800'),
        }

        # ――― make sure we always have a callable ―――
        if show_real_cb is None:
            self.show_real = lambda: False
        elif callable(show_real_cb):
            self.show_real = show_real_cb
        else:                          # a bool was passed in by mistake
            val            = bool(show_real_cb)
            self.show_real = lambda v=val: v

        self._rows = list(rows)            # keep a copy – we'll mutate it in one place only
        self.root  = _Node("ROOT")
        self._build_tree()                 # ← no args any more

    # ------------- public helpers -------------
    def index(self, row, col, parent=QModelIndex()):
        node = parent.internalPointer() if parent.isValid() else self.root
        return self.createIndex(row, col, node.child(row))

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        par  = node.parent
        if par in (None, self.root) or node not in par.children:
            return QModelIndex()            # ← avoids the ValueError you saw
        return self.createIndex(par.row(), 0, par)

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
        if node is None:                             # safety for transient Qt indexes
            return Qt.ItemIsEnabled
        if node.is_group:
            return Qt.ItemIsEnabled | Qt.ItemIsDropEnabled
        base = (Qt.ItemIsSelectable | Qt.ItemIsEnabled |
                Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)     # drag/drop, multi‑select
        if index.column() == 0:
            base |= Qt.ItemIsEditable
        return base

    # ------------- private helpers -------------
    def _build_tree(self):
        """(Re)populate self.root using self._rows."""
        self.root.children.clear()
        groups = {}
        for r in self._rows:
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

        # Only populate self.root.children; do not reset the model here
        return True

    # drag‑export ----------------------------------------------------------
    def mimeTypes(self):                 return [self.MIME]
    def mimeData(self, indexes):
        from PyQt5.QtCore import QMimeData
        ids = []
        for i in indexes:
            if not i.isValid():
                continue
            node = i.internalPointer()
            if not node or node.is_group:
                continue
            ids.append(node.data["id"])
        md = QMimeData()
        md.setData(self.MIME, ",".join(ids).encode())
        return md
    # drag‑import ----------------------------------------------------------
    def supportedDragActions(self):      return Qt.MoveAction
    def supportedDropActions(self):      return Qt.MoveAction

    def dropMimeData(self, data, action, row, col, parent_index):
        if action != Qt.MoveAction or not data.hasFormat(self.MIME):
            return False
        # Determine which node we are dropping onto / into
        target_node = parent_index.internalPointer() if parent_index.isValid() else None

        # If user drops *between* rows Qt gives parent_index = group header, OK
        # If they drop *on* a leaf we walk up until we find a group header.
        while target_node and not getattr(target_node, "is_group", False):
            target_node = target_node.parent

        if not target_node or not getattr(target_node, "is_group", False):
            return False  # cannot determine target group – ignore silently

        group_path = target_node.data
        moved_ids = data.data(self.MIME).data().decode().split(",")
        for mid in moved_ids:
            set_display_info(mid, group=group_path)

        print(f'\n[DND] dropMimeData called on model {id(self)}')
        
        # First emit signal to capture expansion state
        self.layoutAboutToBeChanged.emit()
        
        # Allow a moment for capture to complete
        QCoreApplication.processEvents()
        
        # Do the reset
        self.set_rows(self._rows)
        
        # Signal that model layout is complete (will trigger delayed expansion)
        self.layoutChanged.emit()
        
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Public API – called by browser / drag‑code
    def set_rows(self, rows):
        """Atomic 'replace everything' that's safe for Qt indexes."""
        self.beginResetModel()              # <‑‑ tell Qt old indexes are dead
        self._rows = list(rows)
        self.root  = _Node("ROOT")          # brand‑new root every time
        self._build_tree()
        self.endResetModel()                # <‑‑ new indexes are now valid 