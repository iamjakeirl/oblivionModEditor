from PyQt5.QtWidgets import QTreeView
from PyQt5.QtCore    import Qt, QSortFilterProxyModel, QTimer, QModelIndex
from .jorkTreeViewQT import ModTreeModel
# thin wrapper that wires proxy, search box hookup, etc.
class ModTreeBrowser(QTreeView):
    def __init__(self, rows, *, search_box=None, show_real_cb=None, parent=None):
        super().__init__(parent)
        print(f"\n[MODEL-DEBUG] === ModTreeBrowser.__init__ {id(self)} ===")
        self._model = ModTreeModel(rows, show_real_cb=show_real_cb)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        print(f"[MODEL-DEBUG] self._model = {id(self._model)}, self._proxy = {id(self._proxy)}")
        self.setModel(self._proxy)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setDragDropMode(QTreeView.InternalMove)
        if search_box:
            search_box.textChanged.connect(self._proxy.setFilterFixedString)

        self._expanded_paths = set()
        self._wire_expansion_signals()
        
        # Set up context menu for group headers
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ---------- expansion‑state cache ----------
    def _wire_expansion_signals(self):
        print(f'[MODEL-DEBUG] _wire_expansion_signals called on {id(self)} with model {id(self._model)}')
        self._verify_signal_connections()
        
        # cache whenever either model is about to change
        for sig in (
            self._proxy.layoutAboutToBeChanged,
            self._model.layoutAboutToBeChanged,
        ):
            sig.connect(self._capture_expanded)

        # restore after either model changed
        for sig in (
            self._proxy.layoutChanged,
            self._model.layoutChanged,
        ):
            sig.connect(self._restore_expanded)

        # keep the set up‑to‑date while the user toggles
        self.expanded.connect(
            lambda idx: self._expanded_paths.add(self._path_for_index(idx))
        )
        self.collapsed.connect(
            lambda idx: self._expanded_paths.discard(self._path_for_index(idx))
        )

    def _verify_signal_connections(self):
        """Verify signal connections to model and proxy."""
        print(f"[MODEL-DEBUG] Verifying signal connections for {id(self)}")
        print(f"[MODEL-DEBUG] Using model {id(self._model)} and proxy {id(self._proxy)}")
        
        # Simply log the connections - we can't easily check if they're connected
        # as QObject.receivers() doesn't work with string signal names
        for signal_name in ['layoutAboutToBeChanged', 'layoutChanged']:
            for src_name, src in [('model', self._model), ('proxy', self._proxy)]:
                print(f"[MODEL-DEBUG] {src_name}.{signal_name} should be connected")

    def _capture_expanded(self):
        sender_id = id(self.sender()) if self.sender() else "None"
        print(f'[EXP-DEBUG] _capture_expanded called on view {id(self)} by model {sender_id}')
        print(f'[EXP-DEBUG] Current _model: {id(self._model)}, current view model: {id(self.model())}')
        
        self._expanded_paths = {
            self._path_for_index(idx)
            for idx in self._iter_group_indexes()
            if self.isExpanded(idx)
        }
        print(f'[EXP-DEBUG] captured {len(self._expanded_paths)} expanded paths: {sorted(self._expanded_paths)}')

    def _restore_expanded(self):
        sender_id = id(self.sender()) if self.sender() else "None"
        print(f'[EXP-DEBUG] _restore_expanded called on view {id(self)} by model {sender_id}')
        print(f'[EXP-DEBUG] Current _model: {id(self._model)}, current view model: {id(self.model())}')
        
        # Save paths to a local variable that the timer can access
        paths_to_restore = self._expanded_paths.copy()
        
        # Use a short timer to delay expansion until after the model is fully updated
        def do_restore():
            print(f'[EXP-DEBUG] Delayed restore starting with {len(paths_to_restore)} paths')
            expanded_count = 0
            for idx in self._iter_group_indexes():
                path = self._path_for_index(idx)
                expand = path in paths_to_restore
                if expand:
                    expanded_count += 1
                    self.setExpanded(idx, True)
            print(f'[EXP-DEBUG] Delayed restore completed: {expanded_count}/{len(paths_to_restore)} paths')
            
        # Use a short timer for delayed expansion
        QTimer.singleShot(10, do_restore)

    def _iter_group_indexes(self):
        def walk(parent):
            rows = self.model().rowCount(parent)
            for r in range(rows):
                child = self.model().index(r, 0, parent)
                src   = self._to_source(child)
                node  = src.internalPointer()
                if node and getattr(node, "is_group", False):
                    yield child
                    yield from walk(child)
        yield from walk(QModelIndex())

    def _path_for_index(self, idx):
        src_idx = self._to_source(idx)
        node    = src_idx.internalPointer()
        path = []
        while node and getattr(node, "is_group", False):
            path.append(node.data)
            node = node.parent
        return "/".join(reversed(path))

    # map index from the view's model to the source model (if we are
    # using a proxy); otherwise return the original index.
    def _to_source(self, idx):
        m = self.model()
        return idx if not isinstance(m, QSortFilterProxyModel) else m.mapToSource(idx)

    def refresh_rows(self, new_rows):
        print(f'[MODEL-DEBUG] refresh_rows called on {id(self)} with {len(new_rows)} rows')
        print(f'[MODEL-DEBUG] current model: {id(self._model)}')
        self._model.set_rows(new_rows)

    # Handle context menu for group headers
    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
            
        # Map to source model to check if it's a group
        src_idx = self._to_source(index)
        node = src_idx.internalPointer()
        
        # Only show context menu for group headers
        if not node or not getattr(node, "is_group", False):
            return
            
        # Build and show the context menu
        from PyQt5.QtWidgets import QMenu, QAction, QInputDialog, QMessageBox
        context_menu = QMenu(self)
        rename_action = context_menu.addAction("Rename Group")
        
        action = context_menu.exec_(self.viewport().mapToGlobal(pos))
        if action == rename_action:
            self._rename_group(node)

    def _rename_group(self, group_node):
        """Rename a group and update all contained mods."""
        from PyQt5.QtWidgets import QInputDialog, QMessageBox
        from mod_manager.utils import get_display_info, set_display_info_bulk
        
        # Get current group path
        path_parts = []
        current = group_node
        while current and getattr(current, "is_group", False):
            path_parts.insert(0, current.data)
            current = current.parent
        
        current_path = "/".join(path_parts)
        
        # Get new group name
        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "New group name:", text=group_node.data
        )
        if not ok or not new_name.strip():
            return
        
        # Build the new path
        if len(path_parts) > 1:
            # This is a nested group, keep parent path
            path_parts[-1] = new_name  # Replace just the last part
            new_path = "/".join(path_parts)
        else:
            # This is a top-level group
            new_path = new_name
        
        # Find all mods in this group
        changes = []
        for leaf in self._iter_leaves_in_group(group_node):
            if not isinstance(leaf.data, dict) or "id" not in leaf.data:
                continue
            mod_id = leaf.data["id"]
            changes.append((mod_id, new_path))
        
        if not changes:
            return
            
        # Confirm the change
        reply = QMessageBox.question(
            self,
            "Confirm Group Rename",
            f"Rename group '{current_path}' to '{new_path}'?\nThis will affect {len(changes)} mod(s).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
            
        # Apply changes in bulk
        set_display_info_bulk(changes)
        
        # Refresh the model
        if hasattr(self.window(), "_load_pak_list"):
            self.window()._load_pak_list()
        
    def _iter_leaves_in_group(self, group_node):
        """Iterate through all leaf nodes in a group."""
        for child in group_node.children:
            if getattr(child, "is_group", False):
                yield from self._iter_leaves_in_group(child)
            else:
                yield child 