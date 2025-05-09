from PyQt5.QtWidgets import QTreeView
from PyQt5.QtCore    import Qt, QSortFilterProxyModel, QTimer, QModelIndex, QRegularExpression
from .jorkTreeViewQT import ModTreeModel
# thin wrapper that wires proxy, search box hookup, etc.
class ModTreeBrowser(QTreeView):
    def __init__(self, rows, *, search_box=None, show_real_cb=None, delete_callback=None, parent=None):
        super().__init__(parent)
        print(f"\n[MODEL-DEBUG] === ModTreeBrowser.__init__ {id(self)} ===")
        self._model = ModTreeModel(rows, show_real_cb=show_real_cb)
        # Use custom proxy with advanced filtering
        self._proxy = ModFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        print(f"[MODEL-DEBUG] self._model = {id(self._model)}, self._proxy = {id(self._proxy)}")
        self.setModel(self._proxy)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setDragDropMode(QTreeView.InternalMove)
        if search_box:
            search_box.textChanged.connect(self._proxy.setFilterFixedString)

        # Disable default double-click editing – renaming is handled via context menu
        self.setEditTriggers(QTreeView.NoEditTriggers)

        # Improve drag-drop visual feedback
        self.setStyleSheet(self.styleSheet() + "\nQTreeView::dropIndicator { border: 2px solid #ff9800; }")

        # Apply default dark-theme stylesheet immediately so the header retains
        # the correct colors even before the parent widget later re-applies a
        # per-tab stylesheet. This prevents the fallback to Qt's white header
        # that some users noticed after recent refactors.
        self.setStyleSheet(
            """
QTreeView {
    background: #181818;
    color: #e0e0e0;
    selection-background-color: #333333;
    selection-color: #ff9800;
}
QHeaderView::section {
    background-color: #232323;
    color: #ff9800;
    font-weight: bold;
    border: 1px solid #444;
}
QTreeView::item:selected {
    background:#333333;
    color:#ff9800;
}
            """
        )

        # Optional callbacks (can be injected later via setter)
        self._delete_callback = delete_callback  # fn(list[row_dict]) -> None

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
        # --- Preserve expansion state across data refreshes ---
        # 1) Cache currently expanded group paths
        self._capture_expanded()
        # 2) Update the underlying model
        self._model.set_rows(new_rows)
        # 3) Restore the expansion state on the next Qt tick
        QTimer.singleShot(0, self._restore_expanded)

    # Public helper so parent widgets can swap callbacks after construction
    def set_delete_callback(self, fn):
        """Provide/replace the callback used for Delete action (leaf nodes)."""
        self._delete_callback = fn

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
            
        # Map to source model to check if it's a group
        src_idx = self._to_source(index)
        node = src_idx.internalPointer()
        
        # Only show context menu for group headers
        if not node:
            return

        # ---------- GROUP HEADER ----------
        if getattr(node, "is_group", False):
            from PyQt5.QtWidgets import QMenu, QAction, QInputDialog, QMessageBox
            context_menu = QMenu(self)
            rename_action = context_menu.addAction("Rename Group")
            action = context_menu.exec_(self.viewport().mapToGlobal(pos))
            if action == rename_action:
                self._rename_group(node)
            return  # done

        # ---------- LEAF NODES ----------
        from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox
        context_menu = QMenu(self)

        # Determine current selection (use view-level indexes)
        sel_indexes = self.selectionModel().selectedRows()
        # Ensure the *clicked* item is included (Qt sometimes doesn't include it)
        if src_idx not in [self._to_source(i) for i in sel_indexes]:
            sel_indexes.append(index)

        # Build list of leaf nodes from selected indexes
        leaf_nodes = []
        for idx in sel_indexes:
            sidx = self._to_source(idx)
            n    = sidx.internalPointer()
            if n and not getattr(n, "is_group", False):
                leaf_nodes.append(n)

        if not leaf_nodes:
            return  # nothing useful selected

        many = len(leaf_nodes) > 1

        rename_action = None if many else context_menu.addAction("Rename Display Name…")
        group_action  = context_menu.addAction("Set Group…" + (" (bulk)" if many else ""))
        delete_action = None
        if self._delete_callback:
            delete_action = context_menu.addAction("Delete Mod" + ("s" if many else ""))

        action = context_menu.exec_(self.viewport().mapToGlobal(pos))

        # =========== RENAME ============
        if action == rename_action and not many:
            leaf       = leaf_nodes[0]
            mod_data   = leaf.data
            mod_id     = mod_data["id"]
            current_text = mod_data["real"]

            text, ok = QInputDialog.getText(
                self, "Rename Display Name", "Display Name:", text=current_text
            )
            if not ok:
                return
            new_name = text.strip()
            if not new_name:
                QMessageBox.warning(self, "Invalid Name", "Display name cannot be blank.")
                return

            # Build set of existing display names (to avoid duplicates)
            from mod_manager.utils import get_display_info, set_display_info
            existing = {
                get_display_info(lf.data["id"]).get("display", lf.data["real"]).strip().lower()
                for lf in self._iter_leaves_in_group(self._model.root)
            }
            existing.discard(current_text.strip().lower())

            if new_name.lower() in existing:
                QMessageBox.warning(self, "Duplicate Name",
                                    "That display name is already used by another mod.")
                return

            set_display_info(mod_id, display=new_name)
            self._refresh_parent_views()
            return

        # =========== SET GROUP ============
        elif action == group_action:
            from mod_manager.utils import get_display_info, set_display_info, set_display_info_bulk
            first_mod_id = leaf_nodes[0].data["id"]
            current_group = get_display_info(first_mod_id).get("group", "")
            text, ok = QInputDialog.getText(
                self, "Set Group", "Group:", text=current_group
            )
            if not ok:
                return
            group_val = text.strip()

            if many:
                changes = [(lf.data["id"], group_val) for lf in leaf_nodes]
                set_display_info_bulk(changes)
            else:
                set_display_info(first_mod_id, group=group_val)
            self._refresh_parent_views()
            return

        # =========== DELETE ============
        elif delete_action and action == delete_action and self._delete_callback:
            rows = [lf.data for lf in leaf_nodes]
            try:
                self._delete_callback(rows)
            except Exception as e:
                print(f"[WARN] delete_callback failed: {e}")
            # Parent refresh is responsibility of delete callback (but try anyway)
            QTimer.singleShot(0, self._refresh_parent_views)
            return

        # else: no action selected -> do nothing

    # ---------------- helper to trigger owner window refresh ----------------
    def _refresh_parent_views(self):
        wnd = self.window()
        for fn in ("_load_pak_list", "refresh_lists", "_refresh_ue4ss_status"):
            if hasattr(wnd, fn):
                try:
                    getattr(wnd, fn)()
                except Exception as e:
                    print(f"[WARN] Failed to call {fn}: {e}")

    def _rename_group(self, group_node):
        """Rename a group and update all contained mods."""
        from PyQt5.QtWidgets import QInputDialog
        from mod_manager.utils import set_display_info_bulk
        
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
            
        # Apply changes in bulk
        set_display_info_bulk(changes)
        
        # Refresh the relevant tab so the UI reflects the new grouping
        self._refresh_parent_views()
        
    def _iter_leaves_in_group(self, group_node):
        """Iterate through all leaf nodes in a group."""
        for child in group_node.children:
            if getattr(child, "is_group", False):
                yield from self._iter_leaves_in_group(child)
            else:
                yield child 

    def clear(self):
        """Compatibility helper – mimic QTreeWidget.clear() for QTreeView-based browser.

        Some call-sites (e.g. MainWindow._refresh_ue4ss_status) were written for a
        widget that exposed a .clear() method. Implement the same API here by
        simply resetting the view to an empty data set so we avoid run-time
        AttributeError without duplicating logic elsewhere.
        """
        self.refresh_rows([])

# ---------------- Custom proxy with leaf/group filtering ----------------

class ModFilterProxy(QSortFilterProxyModel):
    """Proxy that searches leaf display names by default; prefix with '#' to search groups."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._group_mode = False  # updated in setFilterFixedString
        # Keep the raw search term (without Qt's wildcard decoration)
        self._search_string = ""  # always lowercase

    # Qt5 compatibility helpers ------------------------------------------------
    def _current_pattern(self):
        # PyQt5 ≤5.15: filterRegularExpression exists; else use filterRegExp/FixedString
        try:
            return self.filterRegularExpression().pattern()
        except AttributeError:
            return str(self.filterRegExp().pattern())

    # API override -------------------------------------------------------------
    def setFilterFixedString(self, pattern: str):
        # Detect group-search mode (leading '#') and strip sentinel
        self._group_mode = pattern.startswith('#')
        if self._group_mode:
            pattern = pattern[1:]

        # Cache the plain, lowercase search term for our custom matcher.
        # We don't rely on Qt's auto-generated wildcard regex because it
        # prepends "^.*" / appends ".*$", which breaks simple
        # `pattern in text` checks.
        self._search_string = pattern.lower().strip()

        # Call base implementation (Qt handles empty ↔ match-all)
        super().setFilterFixedString(pattern)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        # Empty search → accept all (fast path)
        pattern = self._search_string  # already lowercase/stripped
        if not pattern:
            return True

        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        node  = index.internalPointer()

        if node is None:
            return False

        if self._group_mode:
            # ---------- GROUP SEARCH ----------
            if getattr(node, "is_group", False):
                return pattern in str(node.data).lower()
            # Otherwise accept children of matching groups
            return False

        # ---------- LEAF SEARCH (default) ----------
        if getattr(node, "is_group", False):
            # Accept group if any child leaf matches
            child_count = model.rowCount(index)
            for r in range(child_count):
                if self.filterAcceptsRow(r, index):
                    return True
            return False
        else:
            display_text = str(model.data(index, Qt.DisplayRole)).lower()
            return pattern in display_text 