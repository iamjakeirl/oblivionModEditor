# Main window GUI code for Oblivion Remastered Mod Manager
import sys
import os
import shutil
import tempfile
import uuid
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QAbstractItemView, QCheckBox,
    QMenu, QAction, QTabWidget, QInputDialog, QProgressDialog, QFrame, QDialog, QSpacerItem, QSizePolicy,
    QTableWidget, QTableWidgetItem, QTableView, QTreeView, QMenuBar
)
from PyQt5.QtCore import Qt, QEvent, QItemSelectionModel, QUrl, QMimeData, QTimer, QByteArray, QSortFilterProxyModel
from PyQt5.QtGui import (
    QDrag, QPixmap, QColor, QFont, QDragEnterEvent, QDropEvent, QDesktopServices, QKeySequence
)
from mod_manager.utils import (
    migrate_display_keys_if_needed,               #  ← NEW
    get_game_path, SETTINGS_PATH, get_esp_folder, DATA_DIR, open_folder_in_explorer,
    guess_install_type, set_install_type, load_settings, save_settings,
    get_custom_mod_dir_name, _merge_tree, get_display_info, _display_cache,
    set_display_info, set_display_info_bulk
)
from mod_manager.utils import get_install_type     # ensure we can detect Steam/GamePass
from mod_manager.registry import list_esp_files, read_plugins_txt, write_plugins_txt
from mod_manager.pak_manager import (
    list_managed_paks, add_pak, remove_pak, scan_for_installed_paks, 
    reconcile_pak_list, PAK_EXTENSION, RELATED_EXTENSIONS, create_subfolder,
    activate_pak, deactivate_pak, get_pak_target_dir, get_paks_root_dir, ensure_paks_structure
)
import json
import datetime
from pathlib import Path

# Import archive handling libraries
import zipfile
import py7zr
import rarfile
from pyunpack import Archive
import filecmp
import subprocess  # ← will launch MagicLoader.exe

# Note: rarfile library requires unrar executable to be installed on the system or in PATH
# If not available, we'll fall back to pyunpack which uses whatever extractor is available
# See: https://rarfile.readthedocs.io/en/latest/

EXAMPLE_PATH = r"C:\Games\OblivionRemastered"  # Example for user reference
REMEMBER_WINDOW_GEOMETRY = True  # hard‑coded toggle - temp

DEFAULT_LOAD_ORDER = [
    "Oblivion.esm",
    "DLCBattlehornCastle.esp",
    "DLCFrostcrag.esp",
    "DLCHorseArmor.esp",
    "DLCMehrunesRazor.esp",
    "DLCOrrery.esp",
    "DLCShiveringIsles.esp",
    "DLCSpellTomes.esp",
    "DLCThievesDen.esp",
    "DLCVileLair.esp",
    "Knights.esp",
    "AltarESPMain.esp",
    "AltarDeluxe.esp",
    "AltarESPLocal.esp",
]

EXCLUDED_ESPS = [
    'AltarGymNavigation.esp',
    'TamrielLeveledRegion.esp',
]

from ui.install_type_dialog import InstallTypeDialog
from mod_manager.ue4ss_installer import ensure_ue4ss_configs
from ui.jorkTableQT import ModTableModel
from ui.jorkTreeViewQT import ModTreeModel      # NEW import
from ui.jorkTreeBrowser import ModTreeBrowser
from ui.row_builders import rows_from_paks, rows_from_esps
# Custom proxy for advanced searching
from ui.jorkTreeBrowser import ModFilterProxy
# NEW: MagicLoader helpers
from mod_manager.magicloader_installer import (
    magicloader_installed, install_magicloader, uninstall_magicloader,
    reenable_magicloader, get_ml_mods_dir, list_ml_json_mods,
    deactivate_ml_mod, activate_ml_mod, get_magicloader_dir, _target_ml_dir
)
from ui.row_builders import rows_from_magic
# NEW: OBSE64 helpers
from mod_manager.obse64_installer import (
    obse64_installed, install_obse64, uninstall_obse64,
    reenable_obse64, get_obse_plugins_dir, list_obse_plugins,
    activate_obse_plugin, deactivate_obse_plugin, get_obse64_dir, launch_obse64
)
from ui.row_builders import rows_from_obse64_plugins
# NEW: Undo system
from ui.undo_system import UndoStack, UndoAction, ToggleModAction, RenameAction, GroupChangeAction, FileOperationAction, StateSnapshot, PakToggleAction

class PluginsListWidget(QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_in_progress = False
        # Standard stylesheet
        self._normal_stylesheet = self.styleSheet()
        # Stylesheet with hover effect disabled
        self._drag_stylesheet = "QListWidget::item:hover { background: transparent; }"
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self._reorder_callback = None  # Callback for reorder events

    def set_reorder_callback(self, callback):
        self._reorder_callback = callback

    def startDrag(self, supportedActions):
        self._drag_in_progress = True
        # Disable hover highlighting during drag
        self.setStyleSheet(self._drag_stylesheet)
        self.viewport().update()
        
        drag = QDrag(self)
        item = self.currentItem()
        if item:
            pixmap = QPixmap(1, 1)
            pixmap.fill(Qt.transparent)
            drag.setPixmap(pixmap)
            mime = self.model().mimeData(self.selectedIndexes())
            drag.setMimeData(mime)
            result = drag.exec_(supportedActions)
        
        # Re-enable hover highlighting after drag
        self._drag_in_progress = False
        self.setStyleSheet(self._normal_stylesheet)
        self.viewport().update()

    def dropEvent(self, event):
        super().dropEvent(event)
        # Call the reorder callback if set
        if self._reorder_callback:
            self._reorder_callback()

class MainWindow(QWidget):
    def __init__(self):
        # -----------------------------------------------------------
        # One‑time migration of legacy "None|MyMod.pak" display keys
        # (does nothing if the settings flag is already true)
        # -----------------------------------------------------------
        migrate_display_keys_if_needed()

        super().__init__()
        self.setWindowTitle("jorkXL's Oblivion Remastered Mod Manager")
        self.resize(720, 720)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Initialize undo system
        self.undo_stack = UndoStack()
        
        # Create menu bar
        self.menu_bar = QMenuBar(self)
        self.layout.setMenuBar(self.menu_bar)
        
        # Create Edit menu
        edit_menu = self.menu_bar.addMenu("&Edit")
        
        # Undo action
        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.undo_stack.undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)
        
        # Redo action
        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.triggered.connect(self.undo_stack.redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        
        # Connect undo stack signals to update menu items
        self.undo_stack.canUndoChanged.connect(self.undo_action.setEnabled)
        self.undo_stack.canRedoChanged.connect(self.redo_action.setEnabled)
        self.undo_stack.undoTextChanged.connect(self.undo_action.setText)
        self.undo_stack.redoTextChanged.connect(self.redo_action.setText)

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Game path controls
        self.path_layout = QHBoxLayout()
        self.layout.addLayout(self.path_layout)
        self.path_label = QLabel("Game Path:")
        self.path_layout.addWidget(self.path_label)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(f"e.g. {EXAMPLE_PATH}")
        self.path_layout.addWidget(self.path_input)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_path)
        self.path_layout.addWidget(self.browse_btn)
        self.help_path_btn = QPushButton("?")
        self.help_path_btn.setMaximumWidth(50)
        self.help_path_btn.setMinimumWidth(50)
        self.help_path_btn.clicked.connect(self.show_settings_location)
        self.path_layout.addWidget(self.help_path_btn)

        # Add drag-and-drop hint label
        self.drag_drop_layout = QHBoxLayout()
        self.layout.addLayout(self.drag_drop_layout)
        self.drag_drop_label = QLabel("Tip: You can drag and drop .zip or .7z archives onto this window to install mods. <b>RAR files are 50/50 and may need to be installed manually.</b>")
        self.drag_drop_label.setStyleSheet("color: #888888; font-style: italic;")
        self.drag_drop_label.setAlignment(Qt.AlignCenter)
        self.drag_drop_layout.addWidget(self.drag_drop_label)

        # Store the game path for later use
        self.game_path = get_game_path()

        # Create tab widget
        self.notebook = QTabWidget()
        self.layout.addWidget(self.notebook)
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setCursor(Qt.PointingHandCursor)
        self.open_folder_btn.setMinimumHeight(32)
        self.open_folder_btn.setMaximumHeight(32)
        self.open_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #292929;
                color: #ff9800;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
                border: 1px solid #ff9800;
            }
            QPushButton:pressed {
                background-color: #181818;
                color: #ff9800;
            }
        """)
        self.open_folder_btn.clicked.connect(self.open_current_tab_folder)
        self.notebook.setCornerWidget(self.open_folder_btn, Qt.TopRightCorner)

        # Create ESP tab
        self.esp_frame = QWidget()
        self.esp_layout = QVBoxLayout()
        self.esp_frame.setLayout(self.esp_layout)

        # Toggle row (Show real names)
        self.chk_real_esp = QCheckBox("Show real names")
        esp_hdr = QHBoxLayout()
        esp_hdr.addWidget(self.chk_real_esp)
        self.esp_layout.addLayout(esp_hdr)

        # Search bar for ESP mods
        self.esp_search = QLineEdit()
        self.esp_search.setPlaceholderText("Search mods…")
        self.esp_layout.addWidget(self.esp_search)

        # Disabled mods list (shows commented or not-in-plugins.txt mods)
        self.disabled_mods_label = QLabel("Disabled Mods (double-click to enable):")
        self.disabled_mods_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.disabled_mods_label.setAlignment(Qt.AlignCenter)
        self.esp_layout.addWidget(self.disabled_mods_label)
        from ui.row_builders import rows_from_esps
        self.esp_disabled_view = ModTreeBrowser([], search_box=self.esp_search,
                                               show_real_cb=self.chk_real_esp.isChecked, parent=self)
        self.esp_layout.addWidget(self.esp_disabled_view)

        # Create a frame to act as the header bar
        self.enabled_header = QFrame()
        self.enabled_header.setFrameShape(QFrame.StyledPanel)
        self.enabled_header.setFrameShadow(QFrame.Plain)
        enabled_header_layout = QHBoxLayout(self.enabled_header)
        enabled_header_layout.setContentsMargins(8, 2, 8, 2)
        self.enabled_header.setStyleSheet("""
            QFrame {
                background-color: #232323;
                border: 1px solid #333;
            }
            QLabel {
                background-color: transparent;
                border: none;
            }
        """)

        # Create a container for the checkbox with fixed width
        checkbox_container = QWidget()
        checkbox_container.setFixedWidth(360)  # Increased width by 20%
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 5, 0)  # Keep left margin at 0
        checkbox_layout.setSpacing(25)  # Increased spacing between checkboxes
        checkbox_layout.setAlignment(Qt.AlignLeft)  # Align contents to the left
        
        # Checkbox in its container with more minimum width
        self.hide_stock_checkbox = QCheckBox("Hide Default ESPs")
        self.hide_stock_checkbox.setChecked(True)
        self.hide_stock_checkbox.stateChanged.connect(self.refresh_lists)
        self.hide_stock_checkbox.setMinimumWidth(140)  # Set minimum width
        checkbox_layout.addWidget(self.hide_stock_checkbox)

        # Add Load‑Order checkbox with more minimum width
        self.load_order_mode = QCheckBox("Load‑order mode")
        self.load_order_mode.setChecked(False)
        self.load_order_mode.toggled.connect(self._esp_toggle_layout)
        self.load_order_mode.setMinimumWidth(140)  # Set minimum width
        checkbox_layout.addWidget(self.load_order_mode)

        # Add empty widget with same width as checkbox container for balance
        spacer_widget = QWidget()
        spacer_widget.setFixedWidth(360)  # Match checkbox container width

        # Add widgets to main layout
        enabled_header_layout.addWidget(spacer_widget)
        
        # Centered label (no frame/border)
        self.enabled_mods_label = QLabel("Enabled Mods (double-click to disable, drag to reorder):")
        self.enabled_mods_label.setStyleSheet("font-weight: bold; color: #ff9800; border: none; background: transparent;")
        self.enabled_mods_label.setAlignment(Qt.AlignCenter)
        self.enabled_mods_label.setFrameStyle(QFrame.NoFrame)
        enabled_header_layout.addWidget(self.enabled_mods_label, 1, Qt.AlignCenter)

        # Add checkbox container with explicit alignment
        enabled_header_layout.addWidget(checkbox_container, 0, Qt.AlignLeft | Qt.AlignVCenter)

        # Add the header frame to the main layout
        self.esp_layout.addWidget(self.enabled_header)

        self.esp_enabled_view = ModTreeBrowser([], search_box=self.esp_search,
                                              show_real_cb=self.chk_real_esp.isChecked, parent=self)
        self.esp_layout.addWidget(self.esp_enabled_view)

        self.esp_enabled_view.doubleClicked.connect(self._deactivate_esp_row)
        self.esp_disabled_view.doubleClicked.connect(self._activate_esp_row)

        # Update ESP tree labels when "Show real names" toggled
        self.chk_real_esp.toggled.connect(self.esp_enabled_view._model.layoutChanged.emit)
        self.chk_real_esp.toggled.connect(self.esp_disabled_view._model.layoutChanged.emit)

        # Legacy flat lists for load‑order mode  ↓↓↓
        self.disabled_mods_list = PluginsListWidget()
        self.enabled_mods_list  = PluginsListWidget()
        self.enabled_mods_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.enabled_mods_list.set_reorder_callback(self.update_plugins_txt_from_enabled_list)
        # Add them to layout but keep invisible
        self.esp_layout.addWidget(self.disabled_mods_list)
        self.esp_layout.addWidget(self.enabled_mods_list)
        for w in (self.disabled_mods_list, self.enabled_mods_list):
            w.hide()

        # Apply consistent tree styling as in PAK/UE4SS tabs
        tree_stylesheet = """
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
        for view in (self.esp_enabled_view, self.esp_disabled_view):
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True)
            view.expandAll()
            view.setStyleSheet(tree_stylesheet)

        # Attach delete-callback for ESP ModTreeBrowsers so their context menu can delete files
        def _delete_esp_rows(rows):
            for rd in rows:
                try:
                    self.delete_esp_file(rd["real"])
                except Exception as e:
                    print(f"[ESP-DEL] error: {e}")

        self.esp_enabled_view.set_delete_callback(_delete_esp_rows)
        self.esp_disabled_view.set_delete_callback(_delete_esp_rows)

        # Bottom buttons in a horizontal layout
        self.button_row = QHBoxLayout()
        
        self.revert_btn = QPushButton("Revert to Default Load Order")
        self.revert_btn.setMinimumHeight(48)
        self.revert_btn.setMinimumWidth(48)
        self.revert_btn.clicked.connect(self.revert_to_default_order)
        self.button_row.addWidget(self.revert_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(48)
        self.refresh_btn.setMinimumWidth(48)
        self.refresh_btn.clicked.connect(self.refresh_lists)
        self.button_row.addWidget(self.refresh_btn)

        self.esp_layout.addLayout(self.button_row)

        # Add ESP tab to notebook
        self.notebook.addTab(self.esp_frame, "ESP Mods")

        # Create PAK tab
        self.pak_frame = QWidget()
        self.pak_layout = QVBoxLayout()
        self.pak_frame.setLayout(self.pak_layout)

        # Add toggles header for PAK table
        self.chk_real = QCheckBox("Show real names")
        hdr = QHBoxLayout()
        hdr.addWidget(self.chk_real)
        self.pak_layout.insertLayout(0, hdr)

        # Add search box above the tables
        self.pak_search = QLineEdit()
        self.pak_search.setPlaceholderText("Search mods...")
        self.pak_layout.insertWidget(1, self.pak_search)

        # Disabled PAKs label and table
        self.inactive_pak_label = QLabel("Disabled PAKs (double-click to activate):")
        self.inactive_pak_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.inactive_pak_label.setAlignment(Qt.AlignCenter)
        self.pak_layout.insertWidget(2, self.inactive_pak_label)
        self.inactive_pak_view = ModTreeBrowser([], search_box=self.pak_search,
                                                show_real_cb=self.chk_real.isChecked)
        self.pak_layout.insertWidget(3, self.inactive_pak_view)

        # Enabled PAKs label and table
        self.active_pak_label = QLabel("Enabled PAKs (double-click to deactivate):")
        self.active_pak_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.active_pak_label.setAlignment(Qt.AlignCenter)
        self.pak_layout.insertWidget(4, self.active_pak_label)
        self.active_pak_view = ModTreeBrowser([], search_box=self.pak_search,
                                              show_real_cb=self.chk_real.isChecked)
        self.pak_layout.insertWidget(5, self.active_pak_view)

        # PAK control buttons
        self.pak_button_row = QHBoxLayout()
        self.refresh_pak_btn = QPushButton("Refresh PAK List")
        self.refresh_pak_btn.setMinimumHeight(48)
        self.refresh_pak_btn.setMinimumWidth(48)
        self.refresh_pak_btn.clicked.connect(self._load_pak_list)
        self.pak_button_row.addWidget(self.refresh_pak_btn)
        self.pak_layout.addLayout(self.pak_button_row)
        
        # Add PAK tab to notebook
        self.notebook.addTab(self.pak_frame, "PAK Mods")

        # ---------- INSERT NEW MAGICLOADER TAB just below UE4SS tab ---------------
        self.magic_frame = QWidget()
        self.magic_layout = QVBoxLayout(self.magic_frame)

        self.chk_real_magic = QCheckBox("Show real names")
        self.magic_layout.addWidget(self.chk_real_magic)

        self.magic_search = QLineEdit()
        self.magic_search.setPlaceholderText("Search mods…")
        self.magic_layout.addWidget(self.magic_search)

        self.magic_disabled_label = QLabel("Disabled JSON Mods (double‑click to enable):")
        self.magic_disabled_label.setStyleSheet("font-weight:bold; color:#ff9800;")
        self.magic_disabled_label.setAlignment(Qt.AlignCenter)
        self.magic_layout.addWidget(self.magic_disabled_label)

        self.magic_disabled_view = ModTreeBrowser([], search_box=self.magic_search,
                                                  show_real_cb=self.chk_real_magic.isChecked, parent=self)
        self.magic_layout.addWidget(self.magic_disabled_view)

        self.magic_enabled_label = QLabel("Enabled JSON Mods (double‑click to disable):")
        self.magic_enabled_label.setStyleSheet("font-weight:bold; color:#ff9800;")
        self.magic_enabled_label.setAlignment(Qt.AlignCenter)
        self.magic_layout.addWidget(self.magic_enabled_label)

        self.magic_enabled_view = ModTreeBrowser([], search_box=self.magic_search,
                                                 show_real_cb=self.chk_real_magic.isChecked, parent=self)
        self.magic_layout.addWidget(self.magic_enabled_view)

        self.magic_enabled_view.doubleClicked.connect(lambda idx: self._toggle_magic_mod(idx, False))
        self.magic_disabled_view.doubleClicked.connect(lambda idx: self._toggle_magic_mod(idx, True))

        self.chk_real_magic.toggled.connect(self.magic_enabled_view._model.layoutChanged.emit)
        self.chk_real_magic.toggled.connect(self.magic_disabled_view._model.layoutChanged.emit)

        # Apply consistent tree styling as in PAK tab
        tree_stylesheet = """
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
        for view in (self.magic_enabled_view, self.magic_disabled_view):
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True) 
            view.expandAll()
            view.setStyleSheet(tree_stylesheet)

        # status + buttons
        self.magic_status = QLabel("")
        self.magic_status.setAlignment(Qt.AlignCenter)
        self.magic_status.setStyleSheet("font-weight:bold; color:#ff9800;")
        self.magic_layout.addWidget(self.magic_status)

        btn_row = QHBoxLayout()
        self.magic_action_btn = QPushButton()
        self.magic_action_btn.clicked.connect(self._on_magic_action)
        btn_row.addWidget(self.magic_action_btn)

        # --- Run button replaces old Enable/Disable ---
        self.magic_run_btn = QPushButton("Run MagicLoader")
        self.magic_run_btn.clicked.connect(self._launch_magicloader)
        btn_row.addWidget(self.magic_run_btn)

        self.magic_refresh_btn = QPushButton("Refresh")
        self.magic_refresh_btn.clicked.connect(self._refresh_magic_status)
        btn_row.addWidget(self.magic_refresh_btn)

        self.magic_layout.addLayout(btn_row)

        self.notebook.addTab(self.magic_frame, "MagicLoader")
# --------------------------------------------------------------------------

        # --- UE4SS TAB ----------------------------------------------------
        self.ue4ss_frame = QWidget()
        self.ue4ss_layout = QVBoxLayout()
        self.ue4ss_frame.setLayout(self.ue4ss_layout)

        # Toggle row (Show real names)
        self.chk_real_ue4ss = QCheckBox("Show real names")
        ue_hdr = QHBoxLayout()
        ue_hdr.addWidget(self.chk_real_ue4ss)
        self.ue4ss_layout.addLayout(ue_hdr)

        # Search bar for UE4SS mods
        self.ue4ss_search = QLineEdit()
        self.ue4ss_search.setPlaceholderText("Search mods…")
        self.ue4ss_layout.addWidget(self.ue4ss_search)

        # Disabled UE4SS mods list (top)
        self.ue4ss_disabled_label = QLabel("Disabled UE4SS Mods (double-click to enable):")
        self.ue4ss_disabled_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.ue4ss_disabled_label.setAlignment(Qt.AlignCenter)
        self.ue4ss_layout.addWidget(self.ue4ss_disabled_label)
        from ui.row_builders import rows_from_ue4ss
        self.ue4ss_disabled_view = ModTreeBrowser([], search_box=self.ue4ss_search,
                                                 show_real_cb=self.chk_real_ue4ss.isChecked, parent=self)
        self.ue4ss_layout.addWidget(self.ue4ss_disabled_view)

        # Enabled UE4SS mods list (bottom)
        self.ue4ss_enabled_label = QLabel("Enabled UE4SS Mods (double-click to disable):")
        self.ue4ss_enabled_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.ue4ss_enabled_label.setAlignment(Qt.AlignCenter)
        self.ue4ss_layout.addWidget(self.ue4ss_enabled_label)
        self.ue4ss_enabled_view = ModTreeBrowser([], search_box=self.ue4ss_search,
                                                show_real_cb=self.chk_real_ue4ss.isChecked, parent=self)
        self.ue4ss_layout.addWidget(self.ue4ss_enabled_view)

        # Double-click enable/disable for UE4SS mods
        self.ue4ss_enabled_view.doubleClicked.connect(lambda idx: self._toggle_ue4ss_mod(idx, False))
        self.ue4ss_disabled_view.doubleClicked.connect(lambda idx: self._toggle_ue4ss_mod(idx, True))

        # Update UE4SS tree labels when "Show real names" toggled
        self.chk_real_ue4ss.toggled.connect(self.ue4ss_enabled_view._model.layoutChanged.emit)
        self.chk_real_ue4ss.toggled.connect(self.ue4ss_disabled_view._model.layoutChanged.emit)

        # Attach delete-callback for UE4SS ModTreeBrowsers
        def _delete_ue4ss_rows(rows):
            for rd in rows:
                try:
                    self._remove_ue4ss_mod(rd["real"])
                except Exception as e:
                    print(f"[UE4SS-DEL] error: {e}")

        self.ue4ss_enabled_view.set_delete_callback(_delete_ue4ss_rows)
        self.ue4ss_disabled_view.set_delete_callback(_delete_ue4ss_rows)

        # status label (updated by _refresh_ue4ss_status)
        self.ue4ss_status = QLabel("")
        self.ue4ss_status.setAlignment(Qt.AlignCenter)
        self.ue4ss_status.setStyleSheet("font-weight:bold; color:#ff9800;")
        self.ue4ss_layout.addWidget(self.ue4ss_status)

        # button row
        self.ue4ss_btn_row = QHBoxLayout()
        self.ue4ss_action_btn = QPushButton()
        self.ue4ss_action_btn.clicked.connect(self._on_ue4ss_action)
        self.ue4ss_btn_row.addWidget(self.ue4ss_action_btn)

        self.ue4ss_disable_btn = QPushButton()
        self.ue4ss_disable_btn.clicked.connect(self._toggle_ue4ss_enabled)
        self.ue4ss_btn_row.addWidget(self.ue4ss_disable_btn)

        self.ue4ss_refresh_btn = QPushButton("Refresh")
        self.ue4ss_refresh_btn.clicked.connect(self._refresh_ue4ss_status)
        self.ue4ss_btn_row.addWidget(self.ue4ss_refresh_btn)

        self.ue4ss_layout.addLayout(self.ue4ss_btn_row)

        # optional future list of UE4SS script mods can be added here
        self.notebook.addTab(self.ue4ss_frame, "UE4SS")
        # ------------------------------------------------------------------

        # --- OBSE64 TAB ---------------------------------------------------
        self.obse64_frame = QWidget()
        self.obse64_layout = QVBoxLayout()
        self.obse64_frame.setLayout(self.obse64_layout)

        # Toggle row (Show real names)
        self.chk_real_obse64 = QCheckBox("Show real names")
        obse64_hdr = QHBoxLayout()
        obse64_hdr.addWidget(self.chk_real_obse64)
        self.obse64_layout.addLayout(obse64_hdr)

        # Search bar for OBSE64 plugins
        self.obse64_search = QLineEdit()
        self.obse64_search.setPlaceholderText("Search plugins…")
        self.obse64_layout.addWidget(self.obse64_search)

        # Disabled OBSE64 plugins list (top)
        self.obse64_disabled_label = QLabel("Disabled OBSE64 Plugins (double-click to enable):")
        self.obse64_disabled_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.obse64_disabled_label.setAlignment(Qt.AlignCenter)
        self.obse64_layout.addWidget(self.obse64_disabled_label)
        from ui.row_builders import rows_from_obse64_plugins
        self.obse64_disabled_view = ModTreeBrowser([], search_box=self.obse64_search,
                                                  show_real_cb=self.chk_real_obse64.isChecked, parent=self)
        self.obse64_layout.addWidget(self.obse64_disabled_view)

        # Enabled OBSE64 plugins list (bottom)
        self.obse64_enabled_label = QLabel("Enabled OBSE64 Plugins (double-click to disable):")
        self.obse64_enabled_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.obse64_enabled_label.setAlignment(Qt.AlignCenter)
        self.obse64_layout.addWidget(self.obse64_enabled_label)
        self.obse64_enabled_view = ModTreeBrowser([], search_box=self.obse64_search,
                                                 show_real_cb=self.chk_real_obse64.isChecked, parent=self)
        self.obse64_layout.addWidget(self.obse64_enabled_view)

        # Double-click enable/disable for OBSE64 plugins
        self.obse64_enabled_view.doubleClicked.connect(lambda idx: self._toggle_obse64_plugin(idx, False))
        self.obse64_disabled_view.doubleClicked.connect(lambda idx: self._toggle_obse64_plugin(idx, True))

        # Update OBSE64 tree labels when "Show real names" toggled
        self.chk_real_obse64.toggled.connect(self.obse64_enabled_view._model.layoutChanged.emit)
        self.chk_real_obse64.toggled.connect(self.obse64_disabled_view._model.layoutChanged.emit)

        # Attach delete-callback for OBSE64 ModTreeBrowsers
        def _delete_obse64_rows(rows):
            for rd in rows:
                try:
                    self._remove_obse64_plugin(rd["real"])
                except Exception as e:
                    print(f"[OBSE64-DEL] error: {e}")

        self.obse64_enabled_view.set_delete_callback(_delete_obse64_rows)
        self.obse64_disabled_view.set_delete_callback(_delete_obse64_rows)

        # Apply consistent tree styling as in other tabs
        tree_stylesheet = """
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
        for view in (self.obse64_enabled_view, self.obse64_disabled_view):
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True)
            view.expandAll()
            view.setStyleSheet(tree_stylesheet)

        # status label (updated by _refresh_obse64_status)
        self.obse64_status = QLabel("")
        self.obse64_status.setAlignment(Qt.AlignCenter)
        self.obse64_status.setStyleSheet("font-weight:bold; color:#ff9800;")
        self.obse64_layout.addWidget(self.obse64_status)

        # button row
        self.obse64_btn_row = QHBoxLayout()
        
        # Install/Action button (Install, Uninstall, or Re-enable)
        self.obse64_action_btn = QPushButton()
        self.obse64_action_btn.clicked.connect(self._on_obse64_action)
        self.obse64_btn_row.addWidget(self.obse64_action_btn)

        # Browse for archive button
        self.obse64_browse_btn = QPushButton("Browse Archive")
        self.obse64_browse_btn.clicked.connect(self._browse_obse64_archive)
        self.obse64_btn_row.addWidget(self.obse64_browse_btn)

        # Launch OBSE64 button
        self.obse64_launch_btn = QPushButton("Launch OBSE64")
        self.obse64_launch_btn.clicked.connect(self._launch_obse64)
        self.obse64_btn_row.addWidget(self.obse64_launch_btn)

        # Refresh button
        self.obse64_refresh_btn = QPushButton("Refresh")
        self.obse64_refresh_btn.clicked.connect(self._refresh_obse64_status)
        self.obse64_btn_row.addWidget(self.obse64_refresh_btn)

        self.obse64_layout.addLayout(self.obse64_btn_row)

        self.notebook.addTab(self.obse64_frame, "OBSE64")
        # ------------------------------------------------------------------

        # Add a status message area at the bottom of the window
        self.status_frame = QFrame()
        self.status_frame.setFrameShape(QFrame.StyledPanel)
        self.status_frame.setFrameShadow(QFrame.Sunken)
        self.status_frame.setLineWidth(1)
        self.status_frame.setMidLineWidth(0)
        self.status_frame.setStyleSheet("background-color: #f0f0f0;")
        
        self.status_layout = QVBoxLayout(self.status_frame)
        self.status_layout.setContentsMargins(5, 5, 5, 5)
        
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setStyleSheet("color: #333333;")
        self.status_label.setWordWrap(True)
        
        self.status_layout.addWidget(self.status_label)
        self.layout.addWidget(self.status_frame)
        
        # Set the minimum and maximum height for the status area
        self.status_frame.setMinimumHeight(40)
        self.status_frame.setMaximumHeight(80)
        
        # Timer for auto-clearing status messages
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.clear_status)

        self.load_settings()
        if REMEMBER_WINDOW_GEOMETRY:
            s = load_settings()
            geom = s.get("window_geometry")
            if geom:
                try:
                    self.restoreGeometry(QByteArray.fromHex(geom.encode()))
                except Exception:
                    pass
        if ensure_ue4ss_configs(self.game_path):
            self._refresh_ue4ss_status()
        self.refresh_lists()
        # Load PAK mods list
        self._load_pak_list()

        # Create temp directory for extractions
        self.temp_extract_dir = os.path.join(tempfile.gettempdir(), "oblivion_mod_manager")
        os.makedirs(self.temp_extract_dir, exist_ok=True)

        # Apply dark mode stylesheet
        self.setStyleSheet("""
            QWidget {
                background-color: #232323;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10.5pt;
            }
            QTabWidget::pane, QFrame {
                background-color: #232323;
                border: 1px solid #333;
            }
            QTabBar::tab {
                background: #232323;
                color: #e0e0e0;
                border: 1px solid #333;
                padding: 8px 16px;
                margin: 1px;
            }
            QTabBar::tab:selected {
                background: #333;
                color: #ff9800;
                border-bottom: 2px solid #ff9800;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                background: #181818;
                color: #e0e0e0;
                border: 1px solid #444;
            }
            QListWidget, QTreeWidget, QTableWidget, QTableView {
                background: #181818;
                color: #e0e0e0;
                border: 1px solid #444;
                selection-background-color: #333;
                selection-color: #ff9800;
            }
            QListWidget::item:selected {
                background: #333;
                color: #ff9800;
            }
            QPushButton {
                background-color: #292929;
                color: #ff9800;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
                border: 1px solid #ff9800;
            }
            QPushButton:pressed {
                background-color: #181818;
                color: #ff9800;
            }
            QCheckBox, QLabel {
                color: #e0e0e0;
            }
            QCheckBox::indicator:checked {
                background-color: #ff9800;
                border: 1px solid #ff9800;
            }
            QMenu {
                background-color: #232323;
                color: #e0e0e0;
                border: 1px solid #444;
            }
            QMenu::item:selected {
                background-color: #333;
                color: #ff9800;
            }
            QMessageBox {
                background-color: #232323;
                color: #e0e0e0;
            }
            QInputDialog {
                background-color: #232323;
                color: #e0e0e0;
            }
            QProgressDialog {
                background-color: #232323;
                color: #e0e0e0;
            }
            QTreeView::item:selected { background:#333; color:#ff9800; }
        """)

        self._refresh_ue4ss_status()
        self._refresh_magic_status()   # NEW
        self._refresh_obse64_status()  # NEW

        # Connect tab change handler
        self.notebook.currentChanged.connect(self._on_tab_changed)

        # --- SETTINGS TAB --------------------------------------------------
        self.settings_frame = QWidget()
        settings_container = QFrame(self.settings_frame)
        settings_container.setMaximumWidth(460)
        settings_container.setMinimumWidth(360)
        settings_container.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 12px;
                padding: 20px;
                margin: 24px 0 0 24px;
            }
        """)
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        settings_layout.setContentsMargins(20, 16, 20, 20)
        settings_layout.setSpacing(12)

        # Header
        header = QLabel("Pak Install Dir")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 16pt; color: #ff9800; font-weight: bold; margin-bottom: 12px; padding: 0;")
        settings_layout.addWidget(header)

        # Description
        desc = QLabel("Set the name of the folder inside Paks where mods are installed.\nDefault is '~mods'.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("font-size: 11pt; color: #aaaaaa; margin-bottom: 16px;")
        settings_layout.addWidget(desc)

        # Input container with light background
        input_container = QFrame()
        input_container.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-radius: 8px;
                padding: 12px;
            }
            QLineEdit {
                background-color: #303030;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
                font-size: 11pt;
            }
            QPushButton {
                background-color: #3a3a3a;
                color: #ff9800;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px 16px;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #404040;
                border: 1px solid #ff9800;
            }
            QPushButton:pressed {
                background-color: #303030;
            }
        """)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(12)

        self.mod_dir_edit = QLineEdit(get_custom_mod_dir_name())
        self.mod_dir_edit.setMinimumHeight(32)
        self.mod_dir_browse_btn = QPushButton("Browse")
        self.mod_dir_browse_btn.setFixedWidth(100)
        self.mod_dir_browse_btn.setCursor(Qt.PointingHandCursor)
        self.mod_dir_browse_btn.clicked.connect(self._browse_mod_dir_name)

        input_layout.addWidget(self.mod_dir_edit, 1)
        input_layout.addWidget(self.mod_dir_browse_btn, 0)
        settings_layout.addWidget(input_container)

        # Button row with save button
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 16, 0, 0)
        button_row.setSpacing(12)
        button_row.setAlignment(Qt.AlignCenter)

        apply_btn = QPushButton("Save Changes")
        apply_btn.setFixedWidth(150)
        apply_btn.setMinimumHeight(40)
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: #000000;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #ffb74d;
            }
            QPushButton:pressed {
                background-color: #f57c00;
            }
        """)
        apply_btn.clicked.connect(self._save_custom_mod_dir)
        button_row.addWidget(apply_btn)

        settings_layout.addLayout(button_row)

        # Add the settings container to the frame's layout
        outer_layout = QVBoxLayout(self.settings_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        outer_layout.addWidget(settings_container, alignment=Qt.AlignTop | Qt.AlignLeft)
        outer_layout.addStretch(1)

        self.notebook.addTab(self.settings_frame, "Settings")
        # -------------------------------------------------------------------

        print("\n[MODEL-DEBUG] === MainWindow.__init__ STARTING ===")

    def _print_model_relationships(self, context=""):
        """Debug helper to print model relationships."""
        print(f"\n[MODEL-DEBUG] === {context} ===")
        print(f"[MODEL-DEBUG] self.active_pak_model: {id(self.active_pak_model) if hasattr(self, 'active_pak_model') else 'N/A'}")
        print(f"[MODEL-DEBUG] self.inactive_pak_model: {id(self.inactive_pak_model) if hasattr(self, 'inactive_pak_model') else 'N/A'}")
        print(f"[MODEL-DEBUG] self.active_pak_view._model: {id(self.active_pak_view._model) if hasattr(self, 'active_pak_view') else 'N/A'}")
        print(f"[MODEL-DEBUG] self.inactive_pak_view._model: {id(self.inactive_pak_view._model) if hasattr(self, 'inactive_pak_view') else 'N/A'}")

    # Add drag and drop event handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if any URL is a file or directory (not just archives)."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path) or os.path.isdir(file_path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        """Handle drop events for archive files or groups of files/folders."""
        urls = event.mimeData().urls()
        archive_files = []
        non_archives = []
        for url in urls:
            file_path = url.toLocalFile()
            if self._is_supported_archive(file_path):
                archive_files.append(file_path)
            elif os.path.isfile(file_path) or os.path.isdir(file_path):
                non_archives.append(file_path)
        if archive_files:
            event.acceptProposedAction()
            self._process_dropped_archives(archive_files)
        elif non_archives:
            event.acceptProposedAction()
            self._process_dropped_files(non_archives)
        else:
            event.ignore()

    def _is_supported_archive(self, file_path):
        """Check if the file is a supported archive format."""
        if not os.path.isfile(file_path):
            return False
            
        # Get the file extension
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        # Check against supported formats
        return ext in ['.zip', '.7z', '.rar']

    def _process_dropped_archives(self, archive_paths):
        """Process dropped archive files by extracting and installing contents."""
        if not self.game_path:
            self.show_status("Game path not set. Please set your game path before importing mods.", 6000, "error")
            return
        
        # Check that ESP folder exists
        esp_folder = get_esp_folder()
        if not esp_folder:
            self.show_status("ESP folder not found. Please check your game path.", 6000, "error")
            return
        
        # Check that PAK folder exists
        pak_folder = get_pak_target_dir(self.game_path)
        if not pak_folder:
            self.show_status("PAK folder not found. Please check your game path.", 6000, "error")
            return

        # Create progress dialog
        progress = QProgressDialog("Processing archive files...", "Cancel", 0, len(archive_paths), self)
        progress.setWindowTitle("Importing Mods")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        # Process each archive
        for i, archive_path in enumerate(archive_paths):
            progress.setValue(i)
            progress.setLabelText(f"Processing: {os.path.basename(archive_path)}")
            
            if progress.wasCanceled():
                break
                
            # Extract the archive to a temporary directory
            try:
                extract_dir = self._extract_archive(archive_path)
                if not extract_dir:
                    continue
                    
                # --- Abort if MagicLoader.exe is present in the extracted archive ---
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower() == "magicloader.exe":
                            self.show_status("Aborted: MagicLoader installer archive detected. Please do not install MagicLoader as a mod.", 10000, "error")
                            shutil.rmtree(extract_dir, ignore_errors=True)
                            return
                
                # --- Check if this is an OBSE64 archive ---
                is_obse64_archive = False
                obse64_files = []
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower() == "obse64_loader.exe" or (file.lower().startswith("obse64_") and file.lower().endswith(".dll")):
                            is_obse64_archive = True
                            obse64_files.append(os.path.join(root, file))
                
                if is_obse64_archive:
                    # This is an OBSE64 archive, install it directly
                    self._install_obse64_archive(archive_path)
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    continue
                
                # Install the extracted files as regular mod
                self._install_extracted_mod(extract_dir, os.path.basename(archive_path))
                
                # Clean up the temporary directory
                shutil.rmtree(extract_dir, ignore_errors=True)
                
            except Exception as e:
                self.show_status(f"Error processing {os.path.basename(archive_path)}: {str(e)}", 10000, "error")
        
        progress.setValue(len(archive_paths))
        
        # Refresh the lists
        self.refresh_lists()
        self._load_pak_list()

    def _extract_archive(self, archive_path):
        """
        Extract the archive to a temporary directory.
        Returns the path to the extracted directory or None if extraction failed.
        """
        try:
            # Create a unique directory for this extraction
            extract_dir = os.path.join(self.temp_extract_dir, str(uuid.uuid4()))
            os.makedirs(extract_dir, exist_ok=True)
            
            # Get the file extension
            _, ext = os.path.splitext(archive_path)
            ext = ext.lower()
            
            # Extract based on file type
            if ext == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif ext == '.7z':
                with py7zr.SevenZipFile(archive_path, mode='r') as z:
                    z.extractall(extract_dir)
            elif ext == '.rar':
                # Try using rarfile first
                try:
                    # Check if unrar is available
                    if not rarfile.UNRAR_TOOL or not os.path.exists(rarfile.UNRAR_TOOL):
                        # Try to set a default path for common unrar locations
                        for unrar_path in ['unrar', 'C:\\Program Files\\WinRAR\\UnRAR.exe', 'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe']:
                            if os.path.exists(unrar_path):
                                rarfile.UNRAR_TOOL = unrar_path
                                break
                    
                    with rarfile.RarFile(archive_path) as rf:
                        rf.extractall(extract_dir)
                except (rarfile.RarCannotExec, rarfile.RarExecError, rarfile.Error, Exception) as e:
                    # If rarfile fails (likely due to missing unrar), try pyunpack
                    print(f"Rarfile extraction failed: {str(e)}. Falling back to pyunpack.")
                    try:
                        Archive(archive_path).extractall(extract_dir)
                    except Exception as inner_e:
                        raise Exception(f"Failed to extract RAR using both methods: {str(e)}, then: {str(inner_e)}")
            
            return extract_dir
        except Exception as e:
            self.show_status(f"Extraction error: Failed to extract {os.path.basename(archive_path)}: {str(e)}", 10000, "error")
            return None

    def _install_extracted_mod(self, extract_dir, mod_name, force_subfolder=None):
        """
        Install extracted mod files to the appropriate locations.
        Args:
            extract_dir: Directory containing extracted mod files
            mod_name: Name of the mod (for display purposes)
            force_subfolder: If provided, use this as the subfolder for all PAKs
        """
        # --- ~mods and LogicMods merge logic ---
        from mod_manager.pak_manager import get_paks_root_dir, ensure_paks_structure
        ensure_paks_structure(self.game_path)
        paks_root = get_paks_root_dir(self.game_path)
        # Merge ~mods from archive if present
        custom_dir = os.path.join(paks_root, get_custom_mod_dir_name())
        mods_src = os.path.join(extract_dir, "~mods")
        if os.path.isdir(mods_src) and paks_root:
            _merge_tree(mods_src, custom_dir)
            self.show_status(f"Merged ~mods from archive into {custom_dir}.", 5000, "success")
        # Merge LogicMods from archive if present
        logicmods_dirs = []
        for root, dirs, files in os.walk(extract_dir):
            if os.path.basename(root).lower() == "logicmods":
                logicmods_dirs.append(root)

        for logicmods_src in logicmods_dirs:
            logicmods_dest = os.path.join(paks_root, "LogicMods")
            _merge_tree(logicmods_src, logicmods_dest)
            self.show_status(
                f"Merged LogicMods from archive into {logicmods_dest}.",
                5000, "success"
            )
        # --- End ~mods and LogicMods merge logic ---
        
        # Find ESP and PAK files in the extracted content, skipping ~mods and LogicMods
        esp_files = []
        pak_files = []
        skip_dirs = {
            os.path.abspath(os.path.join(extract_dir, "~mods")),
        }
        # also skip any LogicMods folder we just merged
        skip_dirs.update({os.path.abspath(d) for d in logicmods_dirs})
        for root, _, files in os.walk(extract_dir):
            abs_root = os.path.abspath(root)
            # Skip any files inside ~mods or LogicMods in the extracted archive
            if any(abs_root == d or abs_root.startswith(d + os.sep) for d in skip_dirs):
                continue
            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Check if it's an ESP file
                if filename.lower().endswith('.esp'):
                    esp_files.append(filepath)
                
                # Check if it's a PAK file
                elif filename.lower().endswith(PAK_EXTENSION):
                    pak_files.append(filepath)
        
        # --- Detect UE4SS-style folders ---
        ue4ss_mod_folders = []
        shared_mod_folders = []  # special resource folder

        # First, look for the UE4SS/mods/shared structure
        ue4ss_path = Path(extract_dir) / "ue4ss" / "mods" / "shared"
        if ue4ss_path.exists():
            # Found a direct UE4SS/mods/shared structure, add to special case
            shared_mod_folders.append(ue4ss_path)
            print(f"[UE4SS] Found direct shared folder: {ue4ss_path}")

        # Then look for standard mods and any other shared resources
        for root, dirs, files in os.walk(extract_dir):
            root_path = Path(root)
            
            # Skip if we already found this directly
            if root_path == ue4ss_path:
                continue
                
            # Detect any Lua files
            has_lua = any(f.lower().endswith(".lua") for f in files)
            if not has_lua:
                continue
                
            # Check for a shared folder structure anywhere in the path
            if "shared" in root_path.parts:
                for i, part in enumerate(root_path.parts):
                    if part.lower() == "shared":
                        # Found shared folder, get its parent directory
                        shared_parent = Path(*root_path.parts[:i+1])
                        shared_mod_folders.append(shared_parent)
                        print(f"[UE4SS] Found shared folder in path: {shared_parent}")
                        break
            # Standard UE4SS mod detection (scripts folder)
            elif os.path.basename(root).lower() == "scripts":
                mod_root = Path(root).parent  # FolderX
                ue4ss_mod_folders.append(mod_root)
                print(f"[UE4SS] Found standard mod: {mod_root}")
                
        ue4ss_mod_folders = list({p for p in ue4ss_mod_folders})  # dedupe
        shared_mod_folders = list({p for p in shared_mod_folders})
        
        print(f"[UE4SS] Detected {len(ue4ss_mod_folders)} regular mods and {len(shared_mod_folders)} shared resource folders")
        # --- End UE4SS detection ---
        
        # Process ESP files
        installed_esp = 0
        installed_esp_names = []  # Track the names of installed ESPs for auto-enabling
        for esp_path in esp_files:
            try:
                # Get destination path
                esp_name = os.path.basename(esp_path)
                dest_path = os.path.join(get_esp_folder(), esp_name)
                
                # Check if file already exists
                if os.path.exists(dest_path):
                    reply = QMessageBox.question(
                        self,
                        "File Already Exists",
                        f"ESP file {esp_name} already exists. Overwrite?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
                        continue
                
                # Copy the file
                shutil.copy2(esp_path, dest_path)
                
                # Update plugins.txt - add to the list of ESPs to enable
                if not esp_name in DEFAULT_LOAD_ORDER and not esp_name in EXCLUDED_ESPS:
                    installed_esp_names.append(esp_name)
                
                installed_esp += 1
                
            except Exception as e:
                error_msg = f"Failed to install {os.path.basename(esp_path)}: {str(e)}"
                self.show_status(f"Error: {error_msg}", 10000, "error")
                
        if installed_esp:
            self.refresh_lists()  # Refresh ESP tab after installing ESPs
        
        # Process PAK files
        installed_pak = 0
        for pak_path in pak_files:
            try:
                # Determine subfolder based on mod structure
                if force_subfolder is not None:
                    subfolder = force_subfolder
                elif len(pak_files) > 1:
                    subfolder = mod_name.split('.')[0]  # Use archive name without extension
                else:
                    subfolder = None
                # Add the PAK file using existing functionality
                result = add_pak(self.game_path, pak_path, subfolder)
                if result:
                    installed_pak += 1
            
            except Exception as e:
                error_msg = f"Failed to install {os.path.basename(pak_path)}: {str(e)}"
                self.show_status(f"Error: {error_msg}", 10000, "error")
        
        if installed_pak:
            self._load_pak_list()  # Refresh PAK tab after installing PAKs
        
        # --- Install detected UE4SS mods ---
        installed_ue4ss = 0
        if ue4ss_mod_folders:
            from mod_manager.ue4ss_installer import add_ue4ss_mod, ue4ss_installed
            ok, _ = ue4ss_installed(self.game_path)
            if not ok:
                self.show_status("UE4SS not installed – skipping UE4SS mods.", 6000, "warning")
            else:
                for mod_dir in ue4ss_mod_folders:
                    if add_ue4ss_mod(self.game_path, mod_dir):
                        installed_ue4ss += 1
                self._refresh_ue4ss_status()  # Refresh UE4SS tab after installing mods
        # --- Merge any shared resource folders ---
        installed_shared = 0  # Count installed shared resources
        if shared_mod_folders:
            from mod_manager.ue4ss_installer import get_ue4ss_mods_dir
            shared_dest_root = get_ue4ss_mods_dir(self.game_path)
            if shared_dest_root:
                shared_dest = shared_dest_root / "shared"
                for sdir in shared_mod_folders:
                    _merge_tree(sdir, shared_dest)
                    installed_shared += 1
        # --- End UE4SS mod install ---
        
        # --- MagicLoader folder detection (archive may bundle MagicLoader/...) ----
        magic_dirs = []
        for root, dirs, _ in os.walk(extract_dir):
            for d in dirs:
                if d.lower() == "magicloader":
                    magic_dirs.append(os.path.join(root, d))

        installed_ml = 0
        if magic_dirs:
            from mod_manager.magicloader_installer import get_disabled_ml_mods_dir
            import shutil
            dest_root = get_disabled_ml_mods_dir(self.game_path)
            os.makedirs(dest_root, exist_ok=True)

            for mdir in magic_dirs:
                for file in os.listdir(mdir):
                    if file.lower().endswith('.json'):
                        src = os.path.join(mdir, file)
                        dst = os.path.join(dest_root, file)
                        try:
                            shutil.copy2(src, dst)
                            installed_ml += 1
                        except Exception as e:
                            print(f"[MagicLoader] failed to copy {src}: {e}")

            if installed_ml:
                self._refresh_magic_status()
        # --- End MagicLoader folder detection ---
        
        # Enable all installed ESPs by adding them to the end of plugins.txt
        if installed_esp_names:
            plugins = read_plugins_txt()
            # Remove any existing entries (commented or uncommented)
            plugins = [p for p in plugins if p.lstrip('#').strip() not in installed_esp_names]
            # Add all ESPs as enabled (uncommented) at the end
            for esp_name in installed_esp_names:
                plugins.append(esp_name)
            write_plugins_txt(plugins)
        
        # Build summary message with all installed components
        summary_parts = []
        if installed_esp > 0:
            summary_parts.append(f"{installed_esp} ESP")
        if installed_pak > 0:
            summary_parts.append(f"{installed_pak} PAK")
        if installed_ue4ss > 0:
            summary_parts.append(f"{installed_ue4ss} UE4SS mod(s)")
        if installed_shared > 0:
            summary_parts.append(f"{installed_shared} UE4SS shared resource(s)")
        if installed_ml:
            summary_parts.append("MagicLoader")
            
        if not summary_parts:
            summary = f"No installable content found in {mod_name}."
        else:
            summary = f"Installed {', '.join(summary_parts)} from {mod_name}."
            
        self.show_status(summary, 8000, "success")
        
        # Refresh the lists to show the newly enabled ESPs
        self.refresh_lists()

    def show_context_menu(self, position):
        # Determine which list widget triggered the context menu
        sender = self.sender()
        
        # Get selected item
        if sender == self.disabled_mods_list:
            current_item = self.disabled_mods_list.currentItem()
        else:  # sender == self.enabled_mods_list
            current_item = self.enabled_mods_list.currentItem()
            
        if not current_item:
            return
            
        esp_name = current_item.text()
        
        # Don't show context menu for default ESPs
        if esp_name in DEFAULT_LOAD_ORDER:
            return
            
        # Create context menu
        context_menu = QMenu(self)
        
        # Add actions
        delete_action = QAction("Delete ESP File", self)
        delete_action.triggered.connect(lambda: self.delete_esp_file(esp_name))
        context_menu.addAction(delete_action)
        
        disable_action = QAction("Move to Disabled Folder", self)
        disable_action.triggered.connect(lambda: self.move_to_disabled_folder(esp_name))
        context_menu.addAction(disable_action)
        
        # Show context menu at cursor position
        context_menu.exec_(sender.mapToGlobal(position))

    def delete_esp_file(self, esp_name):
        # Ask for confirmation
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion",
            f"Are you sure you want to permanently delete {esp_name}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        # Get ESP folder path
        esp_folder = get_esp_folder()
        if not esp_folder:
            self.show_status("ESP folder not found. Please check your game path.", 6000, "error")
            return
            
        esp_path = os.path.join(esp_folder, esp_name)
        
        # Check if file exists
        if not os.path.exists(esp_path):
            self.show_status(f"File not found: {esp_path}", 6000, "error")
            return
            
        try:
            # Remove from plugins.txt first
            plugins = read_plugins_txt()
            plugins = [p for p in plugins if p.lstrip('#').strip() != esp_name]
            write_plugins_txt(plugins)
            
            # Delete the file
            os.remove(esp_path)
            self.show_status(f"{esp_name} was deleted successfully.", 4000, "success")
            
            # Refresh the lists
            self.refresh_lists()
        except Exception as e:
            self.show_status(f"Failed to delete {esp_name}: {str(e)}", 10000, "error")

    def move_to_disabled_folder(self, esp_name):
        # Ask for confirmation
        reply = QMessageBox.question(
            self, 
            "Confirm Move",
            f"Are you sure you want to move {esp_name} to the disabled folder?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        # Get ESP folder path
        esp_folder = get_esp_folder()
        if not esp_folder:
            self.show_status("ESP folder not found. Please check your game path.", 6000, "error")
            return
            
        esp_path = os.path.join(esp_folder, esp_name)
        
        # Create disabled folder if it doesn't exist
        disabled_folder = os.path.join(esp_folder, "disabled")
        if not os.path.exists(disabled_folder):
            try:
                os.makedirs(disabled_folder)
            except Exception as e:
                self.show_status(f"Failed to create disabled folder: {str(e)}", 10000, "error")
                return
        
        # Check if file exists
        if not os.path.exists(esp_path):
            self.show_status(f"File not found: {esp_path}", 6000, "error")
            return
            
        try:
            # Remove from plugins.txt first
            plugins = read_plugins_txt()
            plugins = [p for p in plugins if p.lstrip('#').strip() != esp_name]
            write_plugins_txt(plugins)
            
            # Move the file
            destination = os.path.join(disabled_folder, esp_name)
            shutil.move(esp_path, destination)
            self.show_status(f"{esp_name} was moved to disabled folder.", 4000, "success")
            
            # Refresh the lists
            self.refresh_lists()
        except Exception as e:
            self.show_status(f"Failed to move {esp_name}: {str(e)}", 10000, "error")

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Oblivion Remastered Folder")
        if path:
            # Show install-type dialog after verifying path is a directory
            default_guess = guess_install_type(path)
            dlg = InstallTypeDialog(default_guess, self)
            if dlg.exec_() != QDialog.Accepted:
                return  # user cancelled
            set_install_type(dlg.selected())
            self.path_input.setText(path)
            # Automatically save the path after browsing
            self.save_game_path()

    def save_game_path(self):
        path = self.path_input.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid Path", "Please enter a valid game directory.")
            return
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            settings = {}
        settings['game_path'] = path
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        self.game_path = path
        # Use status message instead of popup
        self.show_status("Game path saved successfully.", 3000, "success")
        self.refresh_lists()
        self._load_pak_list()  # Also refresh the PAK list
        # Lock the field after saving
        self.path_input.setReadOnly(True)

    def load_settings(self):
        self.game_path = get_game_path()
        if self.game_path:
            self.path_input.setText(self.game_path)
            # Lock the field to prevent accidental edits (use Browse to change)
            self.path_input.setReadOnly(True)

    def refresh_lists(self):
        # short‑circuit when load‑order mode is active
        if getattr(self, "load_order_mode", None) and self.load_order_mode.isChecked():
            self._populate_flat_lists()
            return
        from ui.row_builders import rows_from_esps
        esp_files = list_esp_files()
        if self.hide_stock_checkbox.isChecked():
            # Exclude default ESPs when checkbox is ON
            mod_esps = [esp for esp in esp_files if esp not in DEFAULT_LOAD_ORDER and esp not in EXCLUDED_ESPS]
            default_esps = []
        else:
            # Include default ESPs (they'll always be treated as enabled)
            mod_esps = [esp for esp in esp_files if esp not in EXCLUDED_ESPS]
            default_esps = [esp for esp in esp_files if esp in DEFAULT_LOAD_ORDER]
        plugins_lines = read_plugins_txt()
        enabled_mods = []
        disabled_mods = []
        plugins_in_file = set()
        for line in plugins_lines:
            name = line.lstrip('#').strip()
            if name in mod_esps:
                plugins_in_file.add(name)
                if line.startswith('#'):
                    disabled_mods.append(name)
                else:
                    enabled_mods.append(name)
        for esp in mod_esps:
            if esp not in plugins_in_file:
                disabled_mods.append(esp)
        # Add default ESPs to enabled list if visible
        for d in default_esps:
            if d not in enabled_mods:
                enabled_mods.insert(0, d)  # keep at top
        # Build rows and refresh tree views
        rows = rows_from_esps(enabled_mods, disabled_mods)
        enabled_rows = [r for r in rows if r["active"]]
        disabled_rows = [r for r in rows if not r["active"]]
        self.esp_enabled_view.refresh_rows(enabled_rows)
        self.esp_disabled_view.refresh_rows(disabled_rows)

    def enable_mod(self, item):
        esp = item.text()
        plugins = read_plugins_txt()
        # Remove any commented or uncommented version of this esp
        plugins = [p for p in plugins if p.lstrip('#').strip() != esp]
        # Add as enabled (uncommented) at the end
        plugins.append(esp)
        if write_plugins_txt(plugins):
            self.show_status(f"Enabled mod: {esp}", 3000, "success")
        else:
            self.show_status(f"Error: Failed to enable {esp}", 5000, "error")
        self.refresh_lists()

    def disable_mod(self, item):
        esp = item.text()
        # Don't allow deactivating default ESPs
        if esp in DEFAULT_LOAD_ORDER:
            self.show_status("Default ESPs cannot be deactivated as they are required for the game.", 6000, "warning")
            return
            
        plugins = read_plugins_txt()
        # Remove any commented or uncommented version of this esp
        plugins = [p for p in plugins if p.lstrip('#').strip() != esp]
        # Add as disabled (commented) at the end
        plugins.append(f'#{esp}')
        if write_plugins_txt(plugins):
            self.show_status(f"Disabled mod: {esp}", 3000, "success")
        else:
            self.show_status(f"Error: Failed to disable {esp}", 5000, "error")
        self.refresh_lists()

    def revert_to_default_order(self):
        # Always restore the full default load order
        new_plugins = DEFAULT_LOAD_ORDER.copy()
        # Find extras in the current UI list (not in default, not excluded, not empty)
        current_plugins = [self.enabled_mods_list.item(i).text().lstrip('#').strip() for i in range(self.enabled_mods_list.count()) if self.enabled_mods_list.item(i).text().lstrip('#').strip() not in EXCLUDED_ESPS]
        extras = [p for p in current_plugins if p and p not in DEFAULT_LOAD_ORDER]
        for extra in extras:
            new_plugins.append(f'#{extra}')
        # Write to plugins.txt
        if write_plugins_txt(new_plugins):
            self.show_status("Load order reverted to default. User mods disabled.", 5000, "success")
        else:
            self.show_status("Error: Failed to revert load order.", 5000, "error")
        self.refresh_lists()

    def _load_pak_list(self):
        """Load the list of managed PAK mods into the enabled/disabled tables."""
        if not self.game_path:
            return
        from mod_manager.utils import get_display_info

        reconcile_pak_list(self.game_path)
        pak_mods = list_managed_paks()

        # ── 1) PROPERLY DISCONNECT OLD SIGNALS AND DETACH OLD MODELS ──
        # First, disconnect expansion signals to prevent stale model references
        for _view in (self.active_pak_view, self.inactive_pak_view):
            _view._unwire_expansion_signals()
            
        # Disconnect search box and checkbox connections to old models/proxies
        try:
            self.pak_search.textChanged.disconnect()
            self.chk_real.toggled.disconnect()
        except Exception:
            pass
            
        # Clean up old models and proxies to prevent memory leaks
        for attr_name in ['active_pak_model', 'inactive_pak_model', 'active_pak_proxy', 'inactive_pak_proxy']:
            if hasattr(self, attr_name):
                old_obj = getattr(self, attr_name)
                if old_obj:
                    try:
                        old_obj.deleteLater()
                    except Exception:
                        pass
                    setattr(self, attr_name, None)
            
        # Then detach old models so Qt never keeps indexes from a dead proxy
        for _view in (self.active_pak_view, self.inactive_pak_view):
            _view.setModel(None)

        # ── 2) (Re)build row‑dicts with **display** + **group** information ──
        cache = _display_cache()                                       # O(1) lookup
        def normalize_cb(subfolder):
            import re
            return re.sub(r'^(DisabledMods[\\/]+)', '', subfolder, flags=re.IGNORECASE)
        all_rows = rows_from_paks(pak_mods, cache, normalize_cb)
        enabled_rows = [row for row in all_rows if row["active"]]
        disabled_rows = [row for row in all_rows if not row["active"]]
        # Define the color scheme for trees
        tree_colors = {
            'bg':     QColor('#181818'),
            'fg':     QColor('#e0e0e0'),
            'selbg':  QColor('#333333'),
            'selfg':  QColor('#ff9800'),
        }
        tree_stylesheet = """
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
        # ── 3) Create new models and proxies (but don't connect signals yet) ──
        self.active_pak_model = ModTreeModel(
            enabled_rows,
            show_real_cb=self.chk_real.isChecked,
            colors=tree_colors
        )
        self.inactive_pak_model = ModTreeModel(
            disabled_rows,
            show_real_cb=self.chk_real.isChecked,
            colors=tree_colors
        )

        self.active_pak_proxy = ModFilterProxy(self)
        self.active_pak_proxy.setSourceModel(self.active_pak_model)
        self.active_pak_proxy.setFilterKeyColumn(-1)
        self.inactive_pak_proxy = ModFilterProxy(self)
        self.inactive_pak_proxy.setSourceModel(self.inactive_pak_model)
        self.inactive_pak_proxy.setFilterKeyColumn(-1)

        # ── 4) Replace model and proxy references in views ──
        self.active_pak_view.replace_model_and_proxy(self.active_pak_model, self.active_pak_proxy)
        self.inactive_pak_view.replace_model_and_proxy(self.inactive_pak_model, self.inactive_pak_proxy)
        
        # ── 5) Configure view properties ──
        for view, proxy in (
            (self.active_pak_view,   self.active_pak_proxy),
            (self.inactive_pak_view, self.inactive_pak_proxy)):
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True)
            view.expandAll()                        # default expanded; user can collapse
            view.setStyleSheet(tree_stylesheet)     # use the new tree stylesheet
            try:
                view.doubleClicked.disconnect()
            except Exception:
                pass

        # ── 6) NOW connect signals after all model setup is complete ──
        # Connect toggles to both models (deferred to prevent premature signal emission)
        self.chk_real.toggled.connect(self.active_pak_model.layoutChanged.emit)
        self.chk_real.toggled.connect(self.inactive_pak_model.layoutChanged.emit)

        # Search box filters both proxies (also deferred)
        self.pak_search.textChanged.connect(self.active_pak_proxy.setFilterFixedString)
        self.pak_search.textChanged.connect(self.inactive_pak_proxy.setFilterFixedString)
        # Double-click to activate/deactivate
        # Disconnect previous connections to avoid multiple triggers and stale proxies
        try:
            self.active_pak_view.doubleClicked.disconnect()
            print("[DEBUG] Cleared previous doubleClicked connection for active_pak_view.")
        except Exception:
            print("[DEBUG] No previous doubleClicked connection for active_pak_view to clear.")
        try:
            self.inactive_pak_view.doubleClicked.disconnect()
            print("[DEBUG] No previous doubleClicked connection for inactive_pak_view to clear.")
        except Exception:
            print("[DEBUG] No previous doubleClicked connection for inactive_pak_view to clear.")
        self.active_pak_view.doubleClicked.connect(self._deactivate_pak_view_row)
        print("[DEBUG] Connected doubleClicked for active_pak_view.")
        self.inactive_pak_view.doubleClicked.connect(self._activate_pak_view_row)
        print("[DEBUG] Connected doubleClicked for inactive_pak_view.")
        # Generic ModTreeBrowser already provides context menu; only hook delete callbacks
        def _delete_pak_rows(rows):
            for rd in rows:
                try:
                    self.delete_pak_mod(rd["pak_info"])
                except Exception as e:
                    print(f"[PAK-DEL] error: {e}")

        self.active_pak_view.set_delete_callback(_delete_pak_rows)
        self.inactive_pak_view.set_delete_callback(_delete_pak_rows)

        # DEBUG: Print cache keys and first 5 disabled row ids
        print("_display_cache keys:", list(cache.keys()))
        print("disabled_rows ids:", [r['id'] for r in disabled_rows][:5])

        self._print_model_relationships("_load_pak_list AFTER refresh_rows")
        return

    def _activate_pak_view_row(self, index):
        print('[DND] _activate_pak_view_row called')
        self._print_model_relationships("Before _activate_pak_view_row handling")
        # Activate a PAK from the disabled table
        if not index.isValid():
            return
        src_index = self.inactive_pak_proxy.mapToSource(index)
        is_grp, node = self._is_group_index(src_index)
        if is_grp:
            # bulk‑activate all child leaf nodes (no undo for bulk operations yet)
            for child in node.children:
                if not child.is_group:
                    activate_pak(self.game_path, child.data["pak_info"])
            self._load_pak_list()
            self._print_model_relationships("After _activate_pak_view_row -> _load_pak_list")
            return
        
        # Single mod - use undo system
        pak_info = node.data["pak_info"]
        pak_id = node.data["id"]  # Get ID from row data, not pak_info
        self._toggle_pak_with_undo(pak_id, True)
        self.show_status(f"Activated PAK mod: {pak_info['name']}", 3000, "success")
        self._print_model_relationships("After _activate_pak_view_row -> undo toggle")

    def _deactivate_pak_view_row(self, index):
        print('[DND] _deactivate_pak_view_row called')
        self._print_model_relationships("Before _deactivate_pak_view_row handling")
        # Deactivate a PAK from the enabled table
        if not index.isValid():
            return
        src_index = self.active_pak_proxy.mapToSource(index)
        is_grp, node = self._is_group_index(src_index)
        if is_grp:
            # bulk operations (no undo for bulk operations yet)
            for child in node.children:
                if not child.is_group:
                    deactivate_pak(self.game_path, child.data["pak_info"])
            self._load_pak_list()
            self._print_model_relationships("After _deactivate_pak_view_row -> _load_pak_list")
            return
        
        # Single mod - use undo system
        pak_info = node.data["pak_info"]
        pak_id = node.data["id"]  # Get ID from row data, not pak_info
        self._toggle_pak_with_undo(pak_id, False)
        self.show_status(f"Deactivated PAK mod: {pak_info['name']}", 3000, "success")
        self._print_model_relationships("After _deactivate_pak_view_row -> undo toggle")

    def _show_pak_view_context_menu(self, pos, enabled):
        """
        Context‑menu handler for both enabled/disabled PAK trees.
        Robust against model refreshes: it always queries the *current*
        model attached to the view, so mapToSource() never sees an index
        from the wrong proxy.
        """
        # ----- figure out which view the user clicked in -----
        view = self.active_pak_view if enabled else self.inactive_pak_view
        index = view.indexAt(pos)
        if not index.isValid():
            return

        # ----- get the model(s) presently wired to that view -----
        view_model = view.model()                     # may be proxy or source
        if isinstance(view_model, QSortFilterProxyModel):
            src_index = view_model.mapToSource(index)
            model     = view_model.sourceModel()
        else:
            src_index = index                         # already source
            model     = view_model

        node = src_index.internalPointer()            # our custom _Node

        # Skip group headers (optional)
        if getattr(node, "is_group", False):
            return

        # Extract data for the selected mod
        mod_data = node.data          # dict with 'id', 'pak_info', …
        mod_id   = mod_data["id"]
        pak_info = mod_data["pak_info"]

        # ---------- build and show context menu ----------
        from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox
        context_menu = QMenu(self)
        sel_indexes = view.selectionModel().selectedRows()
        many = len(sel_indexes) > 1
        rename_action = None if many else context_menu.addAction("Rename Display Name…")
        group_action  = context_menu.addAction("Set Group…" + (" (bulk)" if many else ""))
        delete_action = context_menu.addAction("Delete PAK Mod")
        action = context_menu.exec_(view.viewport().mapToGlobal(pos))
        # (The remaining logic is unchanged; just replace every
        #  previous occurrence of 'proxy._rows[row]' / 'table' with
        #  the new local variables mod_data / view.)
        if action == rename_action:
            from mod_manager.utils import get_display_info, set_display_info
            # default text = real file name
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

            # build set of existing display names (to avoid duplicates)
            existing = {
                get_display_info(leaf.data["id"]).get("display", leaf.data["real"]).strip().lower()
                for leaf in _iter_leaf_nodes(model.root)
                if isinstance(leaf.data, dict) and "id" in leaf.data
            }
            existing.discard(current_text.strip().lower())

            if new_name.lower() in existing:
                QMessageBox.warning(self, "Duplicate Name",
                                    "That display name is already used by another mod.")
                return

            set_display_info(mod_id, display=new_name)
            self._load_pak_list()         # refresh view
            return

        elif action == group_action:
            from mod_manager.utils import get_display_info, set_display_info, set_display_info_bulk
            # For bulk, use first selected's group as default
            if many:
                first_index = sel_indexes[0]
                src_index = view.model().mapToSource(first_index) if isinstance(view.model(), QSortFilterProxyModel) else first_index
                node = src_index.internalPointer()
                mod_id = node.data["id"]
            current_group = get_display_info(mod_id).get("group", "")
            text, ok = QInputDialog.getText(
                self, "Set Group", "Group:", text=current_group
            )
            if not ok:
                return
            group_val = text.strip()
            if many:
                # Set group for all selected using bulk helper
                changes = []
                for idx in sel_indexes:
                    src_index = view.model().mapToSource(idx) if isinstance(view.model(), QSortFilterProxyModel) else idx
                    node = src_index.internalPointer()
                    if not getattr(node, "is_group", False):
                        changes.append((node.data["id"], group_val))
                set_display_info_bulk(changes)
            else:
                set_display_info(mod_id, group=group_val)
            self._load_pak_list()
            return

        elif action == delete_action:
            self.delete_pak_mod(pak_info)
            return

    def delete_pak_mod(self, pak_info):
        from PyQt5.QtWidgets import QMessageBox
        from mod_manager.pak_manager import remove_pak
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to permanently delete PAK mod '{pak_info['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        success = remove_pak(self.game_path, pak_info["name"])
        if success:
            self.show_status(f"PAK mod '{pak_info['name']}' was deleted successfully.", 4000, "success")
            self._load_pak_list()
        else:
            self.show_status(f"Failed to delete PAK mod '{pak_info['name']}'.", 10000, "error")

    def show_settings_location(self):
        """Show the user where settings are stored and provide a summary of features and usage (formatted)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings & Features")
        dlg.setMinimumWidth(800)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #232323;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11pt;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #292929;
                color: #ff9800;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
                border: 1px solid #ff9800;
            }
            QPushButton:pressed {
                background-color: #181818;
                color: #ff9800;
            }
        """)
        layout = QVBoxLayout(dlg)
        label = QLabel(f"""
        <div style='min-width:600px;'>
        <b>Settings Location</b><br>
        <span style='color:#888;'>{DATA_DIR}</span><br><br>
        This includes game path and mod configurations.<br><hr>
        <b>jorkXL's Oblivion Remastered Mod Manager Features</b><br>
        <ul style='margin-left: -20px;'>
        <li>Drag-and-drop mod import (<b>.zip</b>, <b>.7z</b>) directly onto the window</li>
        <li>ESP (plugin) and PAK (archive) mod management in separate tabs</li>
        <li>Enable/disable ESP mods and reorder their load order (drag to reorder)</li>
        <li>Hide or show stock ESPs; when hidden, they always load first in default order</li>
        <li>PAK mods can be activated and deactivated.</li>
        <li>All changes to load order are saved to <b>Plugins.txt</b> automatically</li>
        <li>Settings and mod registry are portable and stored in the above folder</li>
        <li>Double-click mods to enable/disable or activate/deactivate</li>
        <li>Right-click mods for more options (delete, move, etc.)</li>
        <li>Game path can be set or changed at any time</li>
        <li>Status messages appear at the bottom for feedback</li>
        </ul>
        <div style='margin-top:10px;'><b>Tips:</b></div>
        <ul style='margin-left: -20px;'>
        <li>Always set your game path before installing mods.</li>
        <li>Use the <b>Refresh</b> button if you make changes outside the manager.</li>
        <li>Backups are recommended before making major changes.</li>
        </ul>
        </div>
        """)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignRight)
        dlg.exec_()

    # Add a method to show status messages
    def show_status(self, message, timeout=0, msg_type="info"):
        """
        Display a message in the status area.
        
        Args:
            message: The message to display
            timeout: Time in milliseconds before message is cleared (0 = no auto-clear)
            msg_type: Type of message - "info", "success", "warning", or "error"
        """
        # Set color based on message type
        if msg_type == "success":
            self.status_label.setStyleSheet("color: #008800;")  # Green for success
        elif msg_type == "warning":
            self.status_label.setStyleSheet("color: #aa6600;")  # Orange for warning
        elif msg_type == "error":
            self.status_label.setStyleSheet("color: #cc0000;")  # Red for error
        else:  # info
            self.status_label.setStyleSheet("color: #333333;")  # Default dark gray
            
        self.status_label.setText(message)
        
        # If a timeout is provided, start the timer to clear the message
        if timeout > 0:
            self.status_timer.start(timeout)
            
    def clear_status(self):
        """Clear the status message."""
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: #333333;")

    def update_plugins_txt_from_enabled_list(self):
        """
        Update plugins.txt to match the current order of enabled_mods_list.
        - If stock ESPs are hidden, default ESPs are always at the top in DEFAULT_LOAD_ORDER order, preserve enabled/disabled state.
        - If stock ESPs are visible, their order in plugins.txt matches the order in the enabled_mods_list (user can reorder them).
        - User mods are always ordered as in enabled_mods_list.
        - Disabled mods not present in the enabled list are appended at the end.
        """
        plugins_lines = read_plugins_txt()
        # Build a dict of current plugin states (enabled/disabled)
        plugin_state = {}
        for line in plugins_lines:
            name = line.lstrip('#').strip()
            plugin_state[name] = line.startswith('#')

        new_order = []
        if self.hide_stock_checkbox.isChecked():
            # Stock ESPs hidden: always at top in DEFAULT_LOAD_ORDER order, preserve enabled/disabled state
            for esp in DEFAULT_LOAD_ORDER:
                if esp in plugin_state:
                    if plugin_state[esp]:
                        new_order.append(f'#{esp}')
                    else:
                        new_order.append(esp)
            # Then user mods from enabled_mods_list
            user_mods_in_list = []
            for i in range(self.enabled_mods_list.count()):
                item_text = self.enabled_mods_list.item(i).text()
                name = item_text.lstrip('#').strip()
                if name not in DEFAULT_LOAD_ORDER and name not in EXCLUDED_ESPS:
                    user_mods_in_list.append(item_text)
            new_order.extend(user_mods_in_list)
        else:
            # Stock ESPs visible: order in plugins.txt matches enabled_mods_list (user can reorder them)
            enabled_in_list = []
            for i in range(self.enabled_mods_list.count()):
                item_text = self.enabled_mods_list.item(i).text()
                name = item_text.lstrip('#').strip()
                if name not in EXCLUDED_ESPS:
                    enabled_in_list.append(item_text)
            new_order.extend(enabled_in_list)
        # Add any remaining mods from plugins.txt (disabled user mods not present in enabled_mods_list)
        enabled_set = set([x.lstrip('#').strip() for x in new_order])
        for line in plugins_lines:
            name = line.lstrip('#').strip()
            if name not in DEFAULT_LOAD_ORDER and name not in EXCLUDED_ESPS and name not in enabled_set:
                new_order.append(line)
        write_plugins_txt(new_order)
        self.show_status("Load order updated.", 2000, "success")

        if self.load_order_mode.isChecked():
            self._populate_flat_lists()

    def open_current_tab_folder(self):
        """
        Open the ESP, PAK, UE4SS, or OBSE64 directory depending on the selected tab.
        """
        current_index = self.notebook.currentIndex()
        if current_index == 0:  # ESP Mods tab
            esp_folder = get_esp_folder()
            if esp_folder:
                open_folder_in_explorer(esp_folder)
            else:
                self.show_status("Could not find ESP folder.", 4000, "error")
        elif current_index == 1:  # PAK Mods tab
            pak_folder = get_pak_target_dir(self.game_path)
            if pak_folder:
                open_folder_in_explorer(pak_folder)
            else:
                self.show_status("Could not find PAK folder.", 4000, "error")
        elif current_index == 2:  # MagicLoader tab
            # 1️⃣ try the actual installed location
            ml_path = get_magicloader_dir(self.game_path)

            # 2️⃣ fall back to the expected target dir (steam vs gamepass)
            if not ml_path:
                from pathlib import Path
                ml_path = _target_ml_dir(Path(self.game_path), get_install_type() or "steam")

            if ml_path and os.path.isdir(ml_path):
                open_folder_in_explorer(str(ml_path))
            else:
                self.show_status("MagicLoader folder not found.", 4000, "error")
        elif current_index == 3:  # UE4SS tab
            from mod_manager.ue4ss_installer import get_ue4ss_bin_dir
            ue4ss_folder = get_ue4ss_bin_dir(self.game_path)
            if ue4ss_folder and os.path.isdir(ue4ss_folder):
                open_folder_in_explorer(ue4ss_folder)
            else:
                self.show_status("UE4SS folder not found.", 4000, "error")
        elif current_index == 4:  # OBSE64 tab
            obse64_folder = get_obse64_dir(self.game_path)
            if obse64_folder and os.path.isdir(obse64_folder):
                open_folder_in_explorer(str(obse64_folder))
            else:
                self.show_status("OBSE64 folder not found.", 4000, "error")

    def _process_dropped_files(self, file_paths):
        """
        Process a group of dropped files/folders as if they were the contents of an archive.
        """
        # Create a unique temp directory
        temp_dir = os.path.join(tempfile.gettempdir(), "oblivion_mod_manager", str(uuid.uuid4()))
        os.makedirs(temp_dir, exist_ok=True)
        # Copy all files/folders into temp_dir
        for path in file_paths:
            dest = os.path.join(temp_dir, os.path.basename(path))
            if os.path.isdir(path):
                shutil.copytree(path, dest)
            else:
                shutil.copy2(path, dest)
        # Determine mod name and subfolder
        if len(file_paths) == 1 and os.path.isdir(file_paths[0]):
            # Use the folder name if a single folder is dropped
            mod_name = os.path.basename(os.path.normpath(file_paths[0]))
            force_subfolder = mod_name
        else:
            # Use a default mod name with timestamp
            mod_name = f"ManualImport_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            force_subfolder = None
        self._install_extracted_mod(temp_dir, mod_name, force_subfolder=force_subfolder)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def _refresh_ue4ss_status(self):
        from mod_manager.ue4ss_installer import ue4ss_installed, get_ue4ss_bin_dir, read_ue4ss_mods_txt
        import os
        if not self.game_path:
            self.ue4ss_status.setText("No game path set.")
            self.ue4ss_enabled_view.clear()
            self.ue4ss_disabled_view.clear()
            return
        ok, version = ue4ss_installed(self.game_path)
        enabled, disabled = read_ue4ss_mods_txt(self.game_path)
        # Filter out default/sentinel mods
        default_mods = {
            "CheatManagerEnablerMod", "ConsoleCommandsMod", "ConsoleEnablerMod",
            "SplitScreenMod", "LineTraceMod", "BPML_GenericFunctions", "BPModLoaderMod", "Keybinds", "shared"
        }
        sentinel = "; Built-in keybinds, do not move up!"
        enabled = [mod for mod in enabled if mod not in default_mods and mod != sentinel]
        disabled = [mod for mod in disabled if mod not in default_mods and mod != sentinel]
        from ui.row_builders import rows_from_ue4ss
        rows = rows_from_ue4ss(enabled, disabled)
        enabled_rows = [r for r in rows if r["active"]]
        disabled_rows = [r for r in rows if not r["active"]]
        # Style and update tree views to match PAK tab
        tree_stylesheet = """
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
        for view in (self.ue4ss_enabled_view, self.ue4ss_disabled_view):
            view.refresh_rows(enabled_rows if view is self.ue4ss_enabled_view else disabled_rows)
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True)
            view.expandAll()
            view.setStyleSheet(tree_stylesheet)
        if ok:
            msg = f"UE4SS detected (version: {version}) in\n{get_ue4ss_bin_dir(self.game_path)}"
        else:
            msg = "UE4SS not installed."
        msg += f"\nEnabled: {len(enabled)} | Disabled: {len(disabled)}"
        self.ue4ss_status.setText(msg)
        self._update_ue4ss_btns()

    def enable_ue4ss_mod(self, item):
        from mod_manager.ue4ss_installer import set_ue4ss_mod_enabled
        mod = item.text()
        set_ue4ss_mod_enabled(self.game_path, mod, True)
        self._refresh_ue4ss_status()

    def disable_ue4ss_mod(self, item):
        from mod_manager.ue4ss_installer import set_ue4ss_mod_enabled
        mod = item.text()
        set_ue4ss_mod_enabled(self.game_path, mod, False)
        self._refresh_ue4ss_status()

    def _install_update_ue4ss(self):
        from mod_manager.ue4ss_installer import install_ue4ss
        from mod_manager.utils import get_install_type, DATA_DIR
        import os, shutil
        # Check for disabled UE4SS
        disabled_dir = DATA_DIR / "disabled_ue4ss"
        if (disabled_dir / "dwmapi.dll").exists() or (disabled_dir / "UE4SS").exists():
            from PyQt5.QtWidgets import QMessageBox
            reply = QMessageBox.warning(
                self,
                "Warning: Disabled UE4SS Present",
                "A disabled version of UE4SS is currently stored in your settings folder.\n"
                "If you proceed with installation, the disabled version will be deleted.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self.show_status("UE4SS install cancelled.", 4000, "info")
                return
            # User confirmed, delete disabled version
            try:
                if (disabled_dir / "dwmapi.dll").exists():
                    os.remove(disabled_dir / "dwmapi.dll")
                if (disabled_dir / "UE4SS").exists():
                    shutil.rmtree(disabled_dir / "UE4SS")
            except Exception as e:
                self.show_status(f"Failed to remove old disabled UE4SS: {e}", 8000, "error")
                return
        if not self.game_path:
            self.show_status("Set game path first.", 6000, "error")
            return
        itype = get_install_type()
        if not itype:
            self.show_status("Install type not set. Re‑select game folder.", 6000, "error")
            return
        dlg = QProgressDialog("Installing UE4SS…", "Cancel", 0, 0, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        ok, err = install_ue4ss(self.game_path, itype)
        dlg.close()
        if ok:
            self.show_status("UE4SS installed.", 5000, "success")
        else:
            self.show_status(f"UE4SS install failed: {err}", 8000, "error")
        self._refresh_ue4ss_status()

    def _uninstall_ue4ss(self):
        from mod_manager.ue4ss_installer import uninstall_ue4ss
        if not self.game_path:
            self.show_status("Set game path first.", 6000, "error")
            return
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.warning(
            self,
            "Uninstall UE4SS",
            "Uninstalling UE4SS will also delete all UE4SS mods/scripts (the entire UE4SS folder).\n\nAre you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            self.show_status("UE4SS uninstall cancelled.", 4000, "info")
            return
        if uninstall_ue4ss(self.game_path):
            self.show_status("UE4SS uninstalled.", 5000, "success")
        else:
            self.show_status("UE4SS uninstall failed.", 8000, "error")
        self._refresh_ue4ss_status()

    def _show_ue4ss_context_menu(self, position):
        sender = self.sender()
        current_item = sender.currentItem()
        if not current_item:
            return
        mod_name = current_item.text()
        # Create context menu
        context_menu = QMenu(self)
        remove_action = QAction("Remove UE4SS Mod", self)
        remove_action.triggered.connect(lambda: self._remove_ue4ss_mod(mod_name))
        context_menu.addAction(remove_action)
        context_menu.exec_(sender.mapToGlobal(position))

    def _remove_ue4ss_mod(self, mod_name):
        from mod_manager.ue4ss_installer import get_ue4ss_mods_dir
        import shutil
        from PyQt5.QtWidgets import QMessageBox
        mods_dir = get_ue4ss_mods_dir(self.game_path)
        mod_path = mods_dir / mod_name if mods_dir else None
        if not mod_path or not mod_path.exists():
            self.show_status(f"Mod folder not found: {mod_name}", 6000, "error")
            return
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to permanently delete UE4SS mod '{mod_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(mod_path)
            # Remove from mods.txt
            from mod_manager.ue4ss_installer import get_ue4ss_bin_dir
            bin_dir = get_ue4ss_bin_dir(self.game_path)
            mods_file = bin_dir / "UE4SS" / "Mods" / "mods.txt" if bin_dir else None
            if mods_file and mods_file.exists():
                lines = mods_file.read_text(encoding="utf-8").splitlines()
                lines = [l for l in lines if not l.strip().startswith(mod_name)]
                mods_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.show_status(f"UE4SS mod '{mod_name}' was deleted successfully.", 4000, "success")
            self._refresh_ue4ss_status()
        except Exception as e:
            self.show_status(f"Failed to delete UE4SS mod '{mod_name}': {str(e)}", 10000, "error")

    def _on_tab_changed(self, idx: int):
        """Fire when user switches tabs; display non‑intrusive UE4SS guidance."""
        if self.notebook.widget(idx) is self.ue4ss_frame:
            self._refresh_ue4ss_status()      # ensure label up‑to‑date
            if "not installed" in self.ue4ss_status.text().lower():
                self.show_status(
                    "UE4SS is optional. Install only if you plan to use mods that require it.",
                    8000,
                    "info"
                )

    def _toggle_ue4ss_enabled(self):
        from mod_manager.ue4ss_installer import get_ue4ss_bin_dir
        from mod_manager.utils import DATA_DIR
        import shutil, os
        bin_dir = get_ue4ss_bin_dir(self.game_path)
        disabled_dir = DATA_DIR / "disabled_ue4ss"
        dll_disabled = disabled_dir / "dwmapi.dll"
        ue4ss_disabled = disabled_dir / "UE4SS"
        # If disabled files exist, enable
        if dll_disabled.exists() or ue4ss_disabled.exists():
            if not bin_dir:
                self.show_status("Game binary directory not found to re-enable UE4SS.", 5000, "error")
                return
            try:
                # Move back dwmapi.dll
                if dll_disabled.exists():
                    shutil.move(str(dll_disabled), str(bin_dir / "dwmapi.dll"))
                # Move back UE4SS folder
                if ue4ss_disabled.exists():
                    dest_folder = bin_dir / "UE4SS"
                    if dest_folder.exists():
                        shutil.rmtree(dest_folder)
                    shutil.move(str(ue4ss_disabled), str(dest_folder))
                self.show_status("UE4SS has been re-enabled.", 6000, "success")
            except Exception as e:
                self.show_status(f"Failed to re-enable UE4SS: {e}", 8000, "error")
                return
        else:
            # Otherwise, disable
            self._disable_ue4ss()
        self._refresh_ue4ss_status()
        self._update_ue4ss_btns()

    def _update_ue4ss_btns(self):
        from mod_manager.ue4ss_installer import ue4ss_installed
        ok, _ = ue4ss_installed(self.game_path)
        if ok:
            self.ue4ss_action_btn.setText("Uninstall UE4SS")
        else:
            self.ue4ss_action_btn.setText("Install UE4SS")
        from mod_manager.utils import DATA_DIR
        disabled_dir = DATA_DIR / "disabled_ue4ss"
        dll_disabled = disabled_dir / "dwmapi.dll"
        ue4ss_disabled = disabled_dir / "UE4SS"
        if dll_disabled.exists() or ue4ss_disabled.exists():
            self.ue4ss_disable_btn.setText("Enable UE4SS")
        else:
            self.ue4ss_disable_btn.setText("Disable UE4SS")

    def _disable_ue4ss(self):
        from mod_manager.ue4ss_installer import get_ue4ss_bin_dir
        from mod_manager.utils import DATA_DIR
        import shutil, os
        bin_dir = get_ue4ss_bin_dir(self.game_path)
        if not bin_dir:
            self.show_status("UE4SS not found to disable.", 5000, "error")
            return
        disabled_dir = DATA_DIR / "disabled_ue4ss"
        os.makedirs(disabled_dir, exist_ok=True)
        # Move dwmapi.dll
        dll_path = bin_dir / "dwmapi.dll"
        if dll_path.exists():
            try:
                shutil.move(str(dll_path), str(disabled_dir / "dwmapi.dll"))
            except Exception as e:
                self.show_status(f"Failed to move dwmapi.dll: {e}", 8000, "error")
                return
        # Move UE4SS folder
        ue4ss_folder = bin_dir / "UE4SS"
        if ue4ss_folder.exists() and ue4ss_folder.is_dir():
            try:
                dest_folder = disabled_dir / "UE4SS"
                if dest_folder.exists():
                    shutil.rmtree(dest_folder)
                shutil.move(str(ue4ss_folder), str(disabled_dir / "UE4SS"))
            except Exception as e:
                self.show_status(f"Failed to move UE4SS folder: {e}", 8000, "error")
                return
        self.show_status("UE4SS has been disabled and preserved in settings folder.", 6000, "success")
        self._refresh_ue4ss_status()

    def _on_ue4ss_action(self):
        from mod_manager.ue4ss_installer import ue4ss_installed
        ok, _ = ue4ss_installed(self.game_path)
        if ok:
            self._uninstall_ue4ss()
        else:
            self._install_update_ue4ss()

    def _save_window_geometry(self):  
        if not REMEMBER_WINDOW_GEOMETRY:  
            return  
        s = load_settings()  
        s["window_geometry"] = self.saveGeometry().toHex().data().decode()  
        save_settings(s)  
    def moveEvent(self, e):  
        super().moveEvent(e)  
        self._save_window_geometry()  
    def resizeEvent(self, e):  
        super().resizeEvent(e)  
        self._save_window_geometry()

    def _save_custom_mod_dir(self):
        name = self.mod_dir_edit.text().strip()
        try:
            from mod_manager.utils import set_custom_mod_dir_name
            old = get_custom_mod_dir_name()
            set_custom_mod_dir_name(name)
            # Prompt for migration if old dir exists and is different
            from mod_manager.pak_manager import get_paks_root_dir
            old_dir = os.path.join(get_paks_root_dir(self.game_path), old)
            new_dir = os.path.join(get_paks_root_dir(self.game_path), name)
            if os.path.isdir(old_dir) and old != name:
                dlg = MigrateModsDialog(old_dir, new_dir, self)
                if dlg.exec_() == QDialog.Accepted:
                    moved = migrate_mods(old_dir, new_dir, self)
                    self.show_status(f"Moved {moved} files from '{old}' to '{name}'.", 6000, "success")
            ensure_paks_structure(self.game_path)         # recreate folder if missing
            self.show_status(
                f"Custom mod folder set to '{name}'. (Existing files stay in '{old}').",
                6000, "success")
            self._load_pak_list()
        except ValueError:
            self.show_status("Folder name invalid or reserved.", 5000, "error")

    def _browse_mod_dir_name(self):
        # Let user pick a folder, but only use the folder name
        from mod_manager.pak_manager import get_paks_root_dir
        base_dir = None
        if self.game_path:
            paks_root = get_paks_root_dir(self.game_path)
            if paks_root:
                current_mod_dir = self.mod_dir_edit.text().strip() or get_custom_mod_dir_name()
                candidate = os.path.join(paks_root, current_mod_dir)
                if os.path.isdir(candidate):
                    base_dir = candidate
                else:
                    base_dir = paks_root
        folder = QFileDialog.getExistingDirectory(self, "Select Mod Subfolder (just pick a folder to use its name)", base_dir or "")
        if folder:
            # Only use the last part of the path as the folder name
            folder_name = os.path.basename(os.path.normpath(folder))
            if folder_name:
                self.mod_dir_edit.setText(folder_name)

    def _is_group_index(self, src_index):
        """Return (is_group, node) where node is internalPointer()."""
        node = src_index.internalPointer()
        return (getattr(node, "is_group", False), node)

    def _esp_toggle_layout(self, on: bool):
        # Remove all widgets from esp_layout except the button row
        widgets = [self.disabled_mods_label, self.esp_disabled_view, self.enabled_header, self.esp_enabled_view,
                   self.disabled_mods_list, self.enabled_mods_list]
        for w in widgets:
            self.esp_layout.removeWidget(w)
            w.setParent(None)
        # Re-add in correct order for the mode
        if on:
            # Load order mode: header, list, header, list
            self.esp_layout.insertWidget(0, self.disabled_mods_label)
            self.esp_layout.insertWidget(1, self.disabled_mods_list)
            self.esp_layout.insertWidget(2, self.enabled_header)
            self.esp_layout.insertWidget(3, self.enabled_mods_list)
            self.disabled_mods_list.show()
            self.enabled_mods_list.show()
            self.esp_disabled_view.hide()
            self.esp_enabled_view.hide()
            self._populate_flat_lists()
        else:
            # Tree mode: header, tree, header, tree
            self.esp_layout.insertWidget(0, self.disabled_mods_label)
            self.esp_layout.insertWidget(1, self.esp_disabled_view)
            self.esp_layout.insertWidget(2, self.enabled_header)
            self.esp_layout.insertWidget(3, self.esp_enabled_view)
            self.disabled_mods_list.hide()
            self.enabled_mods_list.hide()
            self.esp_disabled_view.show()
            self.esp_enabled_view.show()
            self.refresh_lists()

    def _populate_flat_lists(self):
        """Fill legacy QListWidgets from current plugins.txt + disk scan."""
        enabled, disabled = [], []
        esp_files = list_esp_files()
        if self.hide_stock_checkbox.isChecked():
            # Exclude default ESPs when checkbox is ON
            mod_esps = [esp for esp in esp_files if esp not in DEFAULT_LOAD_ORDER and esp not in EXCLUDED_ESPS]
            default_esps = []
        else:
            # Include default ESPs (they'll always be treated as enabled)
            mod_esps = [esp for esp in esp_files if esp not in EXCLUDED_ESPS]
            default_esps = [esp for esp in esp_files if esp in DEFAULT_LOAD_ORDER]
        for line in read_plugins_txt():
            name = line.lstrip('#').strip()
            if name in mod_esps:
                (disabled if line.startswith('#') else enabled).append(name)
        # mods not in plugins.txt are disabled
        for e in mod_esps:
            if e not in enabled and e not in disabled:
                disabled.append(e)

        def fill(widget, items):
            widget.clear()
            for it in items:
                QListWidgetItem(it, widget)

        fill(self.enabled_mods_list, enabled)
        fill(self.disabled_mods_list, disabled)

    def _esp_set_enabled(self, esp_name: str, enabled: bool):
        plugins = read_plugins_txt()
        plugins = [p for p in plugins if p.lstrip('#').strip() != esp_name]
        plugins.append(esp_name if enabled else f'#{esp_name}')
        write_plugins_txt(plugins)

    def _activate_esp_row(self, index):
        src = self.esp_disabled_view._proxy.mapToSource(index)
        node = src.internalPointer()
        if node and not node.is_group:
            esp_name = node.data["real"]
            self._toggle_esp_with_undo(esp_name, True)

    def _deactivate_esp_row(self, index):
        src = self.esp_enabled_view._proxy.mapToSource(index)
        node = src.internalPointer()
        if node and not node.is_group and node.data["real"] not in DEFAULT_LOAD_ORDER:
            esp_name = node.data["real"]
            self._toggle_esp_with_undo(esp_name, False)

    def _toggle_ue4ss_mod(self, index, enable: bool):
        view = self.ue4ss_disabled_view if enable else self.ue4ss_enabled_view
        src = view._proxy.mapToSource(index)
        node = src.internalPointer()
        if node and not node.is_group:
            mod_name = node.data["real"]
            self._toggle_ue4ss_with_undo(mod_name, enable)

    # --------------------------------------------------------------------------
    # MagicLoader helpers
    # --------------------------------------------------------------------------
    def _refresh_magic_status(self):
        if not self.game_path:
            self.magic_status.setText("No game path set.")
            self.magic_enabled_view.clear(); self.magic_disabled_view.clear()
            return
        ok, _ = magicloader_installed(self.game_path)
        if ok:
            msg = f"MagicLoader detected"
        else:
            msg = "MagicLoader not installed."

        from mod_manager.magicloader_installer import list_ml_json_mods
        enabled, disabled = list_ml_json_mods(self.game_path)

        rows = rows_from_magic(enabled, disabled)
        enabled_rows = [r for r in rows if r["active"]]
        disabled_rows = [r for r in rows if not r["active"]]
        
        # Define the color scheme for trees to match PAK tab
        tree_colors = {
            'bg':     QColor('#181818'),
            'fg':     QColor('#e0e0e0'),
            'selbg':  QColor('#333333'),
            'selfg':  QColor('#ff9800'),
        }
        
        # Refresh tree views with consistent styling
        self.magic_enabled_view.refresh_rows(enabled_rows)
        self.magic_disabled_view.refresh_rows(disabled_rows)
        
        # Ensure consistent styling with PAK tab
        tree_stylesheet = """
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
        for view in (self.magic_enabled_view, self.magic_disabled_view):
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True) 
            view.expandAll()
            view.setStyleSheet(tree_stylesheet)

        msg += f"\nEnabled: {len(enabled)} | Disabled: {len(disabled)}"
        self.magic_status.setText(msg)
        self._update_magic_btns()

    def _on_magic_action(self):
        ok, _ = magicloader_installed(self.game_path)
        if ok:
            if uninstall_magicloader(self.game_path):
                self.show_status("MagicLoader uninstalled.", 5000, "success")
            self._refresh_magic_status()
            return

        # ---------- manual‑download flow ----------
        self._prompt_magicloader_manual_install()

    def _update_magic_btns(self):
        ok, _ = magicloader_installed(self.game_path)
        self.magic_action_btn.setText("Uninstall MagicLoader" if ok else "Install MagicLoader")
        # Run button state depends on install status
        self.magic_run_btn.setEnabled(ok)

    # ------------------------------------------------------------------
    # Manual‑download helper UI
    # ------------------------------------------------------------------
    def _prompt_magicloader_manual_install(self):
        """
        Show info box: open Nexus page or browse for already‑downloaded archive.
        """
        from PyQt5.QtWidgets import QMessageBox, QFileDialog
        url = "https://www.nexusmods.com/oblivionremastered/mods/1966?tab=description"

        box = QMessageBox(self)
        box.setWindowTitle("Install MagicLoader")
        box.setIcon(QMessageBox.Information)
        box.setText(
            "MagicLoader must be downloaded manually for now.\n\n"
            "1. Click Open Page to visit Nexus Mods.\n"
            "2. Download the archive (.zip / .7z / .rar).\n"
            "3. Browse and select the archive."
        )
        open_btn   = box.addButton("Open Page",  QMessageBox.ActionRole)
        browse_btn = box.addButton("Browse…",    QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()

        clicked = box.clickedButton()
        if clicked is open_btn:
            QDesktopServices.openUrl(QUrl(url))
            # Re‑prompt so user can browse straight away after download
            self._prompt_magicloader_manual_install()
        elif clicked is browse_btn:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select MagicLoader archive", "",
                "Archives (*.zip *.7z *.rar)"
            )
            if path:
                self._manual_install_magicloader(path)

    def _manual_install_magicloader(self, archive_path: str):
        ok, err = install_magicloader(self.game_path, zip_path=archive_path)
        if ok:
            self.show_status("MagicLoader installed.", 5000, "success")
        else:
            self.show_status(f"MagicLoader install failed: {err}", 8000, "error")
        self._refresh_magic_status()

    def _toggle_magic_enabled(self):
        from mod_manager.utils import DATA_DIR
        disabled_root = Path(DATA_DIR)/"disabled_magicloader"/"MagicLoader"
        ok, _ = magicloader_installed(self.game_path)
        if ok:
            # disable
            if uninstall_magicloader(self.game_path):
                self.show_status("MagicLoader disabled.", 5000, "success")
        elif disabled_root.exists():
            if reenable_magicloader(self.game_path):
                self.show_status("MagicLoader re‑enabled.", 5000, "success")
        self._refresh_magic_status()

    def _toggle_magic_mod(self, index, enable: bool):
        view = self.magic_disabled_view if enable else self.magic_enabled_view
        src  = view._proxy.mapToSource(index)
        node = src.internalPointer()
        if node and not node.is_group:
            name = node.data["real"]
            # Use undo system for the toggle
            self._toggle_magic_with_undo(name, enable)

    # ------------------------------------------------------------------
    # Launch MagicLoader executable
    # ------------------------------------------------------------------
    def _launch_magicloader(self):
        from mod_manager.magicloader_installer import get_magicloader_dir
        import os

        ml_dir = get_magicloader_dir(self.game_path)
        if not ml_dir:
            self.show_status("MagicLoader not installed.", 4000, "error")
            return
        exe = os.path.join(ml_dir, "MagicLoader.exe")
        if not os.path.isfile(exe):
            self.show_status("MagicLoader.exe not found.", 4000, "error")
            return
        try:
            subprocess.Popen([exe], cwd=ml_dir)
            self.show_status("MagicLoader launched.", 3000, "success")
        except Exception as e:
            self.show_status(f"Failed to launch MagicLoader: {e}", 8000, "error")

    # -------------------------------------------------------------------------
    # OBSE64 Methods
    # -------------------------------------------------------------------------

    def _refresh_obse64_status(self):
        """Refresh OBSE64 status and plugin lists."""
        if not self.game_path:
            self.obse64_status.setText("No game path set.")
            self.obse64_enabled_view.clear()
            self.obse64_disabled_view.clear()
            return
        
        # Check if OBSE64 is installed
        is_installed, version_or_error = obse64_installed(self.game_path)
        
        if is_installed:
            # Get plugin lists
            enabled, disabled = list_obse_plugins(self.game_path)
            
            # Build rows for tree display
            rows = rows_from_obse64_plugins(enabled, disabled)
            enabled_rows = [r for r in rows if r["active"]]
            disabled_rows = [r for r in rows if not r["active"]]
            
            # Apply tree styling and update views
            tree_stylesheet = """
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
            for view in (self.obse64_enabled_view, self.obse64_disabled_view):
                view.refresh_rows(enabled_rows if view is self.obse64_enabled_view else disabled_rows)
                view.setHeaderHidden(False)
                view.setRootIsDecorated(True)
                view.expandAll()
                view.setStyleSheet(tree_stylesheet)
            
            # Update status message
            obse_dir = get_obse64_dir(self.game_path)
            msg = f"OBSE64 detected (version: {version_or_error}) in\n{obse_dir}"
            msg += f"\nEnabled: {len(enabled)} | Disabled: {len(disabled)}"
        else:
            # Clear views and show error/not installed status
            self.obse64_enabled_view.clear()
            self.obse64_disabled_view.clear()
            msg = version_or_error  # This will be the error message
        
        self.obse64_status.setText(msg)
        self._update_obse64_btns()

    def _update_obse64_btns(self):
        """Update OBSE64 button states based on installation status."""
        is_installed, version_or_error = obse64_installed(self.game_path)
        
        # Check if we have disabled OBSE64 backup
        from mod_manager.utils import DATA_DIR
        disabled_dir = DATA_DIR / "disabled_obse64"
        has_disabled = disabled_dir.exists() and any(disabled_dir.glob("obse64_*"))
        
        if is_installed:
            self.obse64_action_btn.setText("Uninstall")
            self.obse64_action_btn.setEnabled(True)
            self.obse64_browse_btn.setEnabled(False)  # Don't allow install over existing
            self.obse64_launch_btn.setEnabled(True)
        elif has_disabled:
            self.obse64_action_btn.setText("Re-enable")
            self.obse64_action_btn.setEnabled(True)
            self.obse64_browse_btn.setEnabled(True)  # Allow fresh install
            self.obse64_launch_btn.setEnabled(False)
        else:
            self.obse64_action_btn.setText("Install")
            self.obse64_action_btn.setEnabled(False)  # Needs browse first
            self.obse64_browse_btn.setEnabled(True)
            self.obse64_launch_btn.setEnabled(False)

    def _on_obse64_action(self):
        """Handle OBSE64 action button (Install/Uninstall/Re-enable)."""
        if not self.game_path:
            self.show_status("Set game path first.", 6000, "error")
            return
        
        is_installed, _ = obse64_installed(self.game_path)
        
        if is_installed:
            self._uninstall_obse64()
        else:
            # Check if we have disabled backup to re-enable
            from mod_manager.utils import DATA_DIR
            disabled_dir = DATA_DIR / "disabled_obse64"
            if disabled_dir.exists() and any(disabled_dir.glob("obse64_*")):
                self._reenable_obse64()
            else:
                # Need to browse for archive
                self.show_status("Use 'Browse Archive' button to select OBSE64 archive for installation.", 6000, "info")

    def _browse_obse64_archive(self):
        """Browse for OBSE64 archive and install it."""
        if not self.game_path:
            self.show_status("Set game path first.", 6000, "error")
            return
        
        # Check Steam restriction
        from mod_manager.utils import get_install_type
        install_type = get_install_type()
        if install_type != "steam":
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "OBSE64 Not Supported",
                f"OBSE64 is only supported on Steam installations.\n"
                f"Your installation type: {install_type or 'Unknown'}\n\n"
                f"Please use a Steam installation of Oblivion Remastered to use OBSE64.",
                QMessageBox.Ok
            )
            return
        
        # Browse for archive
        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OBSE64 Archive",
            "",
            "Archive Files (*.zip *.7z *.rar);;All Files (*)"
        )
        
        if not archive_path:
            return
        
        self._install_obse64_archive(archive_path)

    def _install_obse64_archive(self, archive_path):
        """Install OBSE64 from the given archive path."""
        # Show progress dialog
        dlg = QProgressDialog("Installing OBSE64...", "Cancel", 0, 0, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        
        def progress_callback(message):
            dlg.setLabelText(message)
            QApplication.processEvents()
        
        try:
            success, message = install_obse64(self.game_path, archive_path, progress_callback)
            dlg.close()
            
            if success:
                self.show_status(message, 5000, "success")
            else:
                self.show_status(f"OBSE64 installation failed: {message}", 8000, "error")
        except Exception as e:
            dlg.close()
            self.show_status(f"OBSE64 installation error: {e}", 8000, "error")
        
        self._refresh_obse64_status()

    def _uninstall_obse64(self):
        """Uninstall OBSE64 (move to disabled folder)."""
        from PyQt5.QtWidgets import QMessageBox
        
        reply = QMessageBox.warning(
            self,
            "Uninstall OBSE64",
            "This will disable OBSE64 by moving its files to a backup location.\n"
            "OBSE64 plugins will remain in place but won't be loaded.\n\n"
            "You can re-enable OBSE64 later using the 'Re-enable' button.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            self.show_status("OBSE64 uninstall cancelled.", 4000, "info")
            return
        
        if uninstall_obse64(self.game_path):
            self.show_status("OBSE64 disabled successfully.", 5000, "success")
        else:
            self.show_status("OBSE64 uninstall failed.", 8000, "error")
        
        self._refresh_obse64_status()

    def _reenable_obse64(self):
        """Re-enable OBSE64 from disabled backup."""
        if reenable_obse64(self.game_path):
            self.show_status("OBSE64 re-enabled successfully.", 5000, "success")
        else:
            self.show_status("OBSE64 re-enable failed.", 8000, "error")
        
        self._refresh_obse64_status()

    def _launch_obse64(self):
        """Launch the game via OBSE64 loader."""
        if not self.game_path:
            self.show_status("Set game path first.", 6000, "error")
            return
        
        is_installed, _ = obse64_installed(self.game_path)
        if not is_installed:
            self.show_status("OBSE64 is not installed.", 6000, "error")
            return
        
        if launch_obse64(self.game_path):
            self.show_status("Launching game via OBSE64...", 3000, "success")
        else:
            self.show_status("Failed to launch OBSE64.", 6000, "error")

    def _toggle_obse64_plugin(self, index, enable: bool):
        """Toggle OBSE64 plugin enabled/disabled state."""
        if not index.isValid():
            return
        
        # Get the plugin name from the model
        model = index.model()
        if hasattr(model, '_model') and hasattr(model._model, 'data'):
            # This is a proxy model, get the underlying model
            source_index = model.mapToSource(index)
            row_data = model._model.data(source_index, Qt.UserRole)
        else:
            row_data = model.data(index, Qt.UserRole)
        
        if not row_data or 'obse64_info' not in row_data:
            return
        
        plugin_name = row_data['obse64_info']['name']
        
        # Use undo system for toggle
        self._toggle_obse64_with_undo(plugin_name, enable)
        
        # Show status message
        action = "enabled" if enable else "disabled"
        self.show_status(f"OBSE64 plugin '{plugin_name}' {action}.", 3000, "success")

    def _remove_obse64_plugin(self, plugin_name):
        """Remove OBSE64 plugin permanently."""
        from PyQt5.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to permanently delete OBSE64 plugin '{plugin_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            plugins_dir = get_obse_plugins_dir(self.game_path)
            if not plugins_dir:
                self.show_status("OBSE64 plugins directory not found.", 6000, "error")
                return
            
            # Check both enabled and disabled locations
            plugin_path = plugins_dir / plugin_name
            disabled_path = plugins_dir / "disabled" / plugin_name
            
            removed = False
            if plugin_path.exists():
                plugin_path.unlink()
                removed = True
            if disabled_path.exists():
                disabled_path.unlink()
                removed = True
            
            if removed:
                self.show_status(f"OBSE64 plugin '{plugin_name}' was deleted successfully.", 4000, "success")
                self._refresh_obse64_status()
            else:
                self.show_status(f"OBSE64 plugin '{plugin_name}' not found.", 6000, "error")
        except Exception as e:
            self.show_status(f"Failed to delete OBSE64 plugin '{plugin_name}': {str(e)}", 8000, "error")

    # =============================================================================
    # UNDO SYSTEM INTEGRATION HELPERS
    # =============================================================================
    
    def _create_toggle_action(self, mod_id: str, tab_type: str, old_state: bool, new_state: bool, 
                             toggle_callback, refresh_callback) -> ToggleModAction:
        """Create a toggle action for the undo system."""
        return ToggleModAction(mod_id, tab_type, old_state, new_state, 
                              toggle_callback, refresh_callback)
                              
    def _create_rename_action(self, target_id: str, old_name: str, new_name: str,
                             rename_callback, refresh_callback) -> RenameAction:
        """Create a rename action for the undo system."""
        return RenameAction(target_id, old_name, new_name, rename_callback, refresh_callback)
        
    def _create_group_action(self, mod_id: str, old_group: str, new_group: str,
                            group_callback, refresh_callback) -> GroupChangeAction:
        """Create a group change action for the undo system.""" 
        return GroupChangeAction(mod_id, old_group, new_group, group_callback, refresh_callback)
        
    def _execute_with_undo(self, action: UndoAction) -> bool:
        """Execute an action and add it to the undo stack."""
        print(f'[UNDO-DEBUG] _execute_with_undo called with action: {action.description}')
        result = self.undo_stack.push(action)
        print(f'[UNDO-DEBUG] undo_stack.push returned: {result}')
        print(f'[UNDO-DEBUG] undo_stack.can_undo: {self.undo_stack.can_undo()}')
        print(f'[UNDO-DEBUG] undo_stack actions count: {len(self.undo_stack.actions)}')
        return result

    # =============================================================================
    # UNDO-ENABLED TOGGLE WRAPPERS
    # =============================================================================
    
    def _toggle_pak_with_undo(self, pak_id: str, enable: bool):
        """Toggle PAK mod with undo support."""
        print(f'[UNDO-DEBUG] _toggle_pak_with_undo called: pak_id={pak_id}, enable={enable}')
        # Get current state and pak_info
        from mod_manager.pak_manager import list_managed_paks
        all_paks = list_managed_paks()
        
        # Find current state by reconstructing the ID from pak data
        current_state = False
        
        for pak in all_paks:
            # Reconstruct the pak_id from pak data: "subfolder|name"
            pak_subfolder = pak.get('subfolder', '') or ''
            reconstructed_id = f"{pak_subfolder}|{pak['name']}"
            
            if reconstructed_id == pak_id:
                current_state = pak.get('active', False)
                break
        
        print(f'[UNDO-DEBUG] current_state: {current_state}, desired state: {enable}')
        
        if current_state == enable:
            print(f'[UNDO-DEBUG] Already in desired state, returning early')
            return  # Already in desired state
            
        # Use special PAK action that looks up fresh pak_info at execution time
        action = PakToggleAction(
            pak_id, current_state, enable, 
            self.game_path, self._load_pak_list
        )
        print(f'[UNDO-DEBUG] Created PakToggleAction: {action.description}')
        self._execute_with_undo(action)
        
    def _toggle_esp_with_undo(self, esp_name: str, enable: bool):
        """Toggle ESP mod with undo support."""
        # Get current state from plugins.txt
        plugins_lines = read_plugins_txt()
        current_state = False
        
        # Check if the ESP is currently enabled (uncommented in plugins.txt)
        for line in plugins_lines:
            clean_name = line.lstrip('#').strip()
            if clean_name == esp_name:
                current_state = not line.startswith('#')  # enabled if not commented
                break
        
        if current_state == enable:
            return  # Already in desired state
            
        # Create toggle action
        def toggle_callback(mod_id, new_state):
            self._esp_set_enabled(mod_id, new_state)
            
        action = self._create_toggle_action(
            esp_name, "ESP", current_state, enable,
            toggle_callback, self.refresh_lists
        )
        self._execute_with_undo(action)
        
    def _toggle_ue4ss_with_undo(self, mod_name: str, enable: bool):
        """Toggle UE4SS mod with undo support.""" 
        from mod_manager.ue4ss_installer import read_ue4ss_mods_txt
        
        # Get current state from mods.txt file, not folder existence
        enabled_mods, disabled_mods = read_ue4ss_mods_txt(self.game_path)
        current_state = mod_name in enabled_mods
        
        if current_state == enable:
            return  # Already in desired state
            
        # Create toggle action
        def toggle_callback(mod_id, new_state):
            from mod_manager.ue4ss_installer import set_ue4ss_mod_enabled
            set_ue4ss_mod_enabled(self.game_path, mod_id, new_state)
            
        action = self._create_toggle_action(
            mod_name, "UE4SS", current_state, enable,
            toggle_callback, self._refresh_ue4ss_status
        )
        self._execute_with_undo(action)
        
    def _toggle_magic_with_undo(self, mod_name: str, enable: bool):
        """Toggle MagicLoader mod with undo support."""
        from mod_manager.magicloader_installer import list_ml_json_mods
        
        enabled_mods, disabled_mods = list_ml_json_mods(self.game_path)
        current_state = any(m == mod_name for m in enabled_mods)
        
        if current_state == enable:
            return  # Already in desired state
            
        # Create toggle action
        def toggle_callback(mod_id, new_state):
            from mod_manager.magicloader_installer import activate_ml_mod, deactivate_ml_mod
            if new_state:
                activate_ml_mod(self.game_path, mod_id)
            else:
                deactivate_ml_mod(self.game_path, mod_id)
                
        action = self._create_toggle_action(
            mod_name, "MagicLoader", current_state, enable,
            toggle_callback, self._refresh_magic_status
        )
        self._execute_with_undo(action)
        
    def _toggle_obse64_with_undo(self, plugin_name: str, enable: bool):
        """Toggle OBSE64 plugin with undo support."""
        enabled_plugins, disabled_plugins = list_obse_plugins(self.game_path)
        current_state = any(p == plugin_name for p in enabled_plugins)
        
        if current_state == enable:
            return  # Already in desired state
            
        # Create toggle action
        def toggle_callback(mod_id, new_state):
            if new_state:
                activate_obse_plugin(self.game_path, mod_id)
            else:
                deactivate_obse_plugin(self.game_path, mod_id)
                
        action = self._create_toggle_action(
            plugin_name, "OBSE64", current_state, enable,
            toggle_callback, self._refresh_obse64_status
        )
        self._execute_with_undo(action)

    # =============================================================================
    # UNDO-ENABLED RENAME/GROUP WRAPPERS
    # =============================================================================
    
    def _rename_with_undo(self, mod_id: str, old_name: str, new_name: str, refresh_callback):
        """Rename mod with undo support."""
        def rename_callback(target_id, name):
            set_display_info(target_id, display=name)
            
        action = self._create_rename_action(mod_id, old_name, new_name, 
                                          rename_callback, refresh_callback)
        self._execute_with_undo(action)
        
    def _change_group_with_undo(self, mod_id: str, old_group: str, new_group: str, refresh_callback):
        """Change mod group with undo support."""
        def group_callback(target_id, group):
            set_display_info(target_id, group=group)
            
        action = self._create_group_action(mod_id, old_group, new_group,
                                         group_callback, refresh_callback)
        self._execute_with_undo(action)


class MigrateModsDialog(QDialog):
    def __init__(self, old_dir, new_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Migrate Mods")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #232323;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11pt;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #292929;
                color: #ff9800;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
                border: 1px solid #ff9800;
            }
            QPushButton:pressed {
                background-color: #181818;
                color: #ff9800;
            }
        """)
        layout = QVBoxLayout(self)
        msg = QLabel(f"Move all mods from <b>{old_dir}</b> to <b>{new_dir}</b>?\nThis will preserve all subfolders and files.")
        msg.setWordWrap(True)
        msg.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(msg)
        btn_row = QHBoxLayout()
        self.ok_btn = QPushButton("Migrate")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)


def migrate_mods(old_dir, new_dir, parent=None):
    import shutil, os
    from PyQt5.QtWidgets import QProgressDialog
    if not os.path.isdir(old_dir):
        return 0
    # Count files to move
    file_list = []
    for root, _, files in os.walk(old_dir):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, old_dir)
            dst = os.path.join(new_dir, rel)
            file_list.append((src, dst))
    if not file_list:
        return 0
    dlg = QProgressDialog("Migrating mods...", "Cancel", 0, len(file_list), parent)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumWidth(400)
    dlg.show()
    moved = 0
    for i, (src, dst) in enumerate(file_list):
        if dlg.wasCanceled():
            break
        dlg.setValue(i)
        dlg.setLabelText(f"Moving: {os.path.basename(src)}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.move(src, dst)
            moved += 1
        except Exception:
            pass
    dlg.setValue(len(file_list))
    return moved

def _iter_leaf_nodes(node):
    """Depth‑first generator that yields every leaf (non‑group) node."""
    stack = [node]
    while stack:
        n = stack.pop()
        if getattr(n, "is_group", False):
            stack.extend(n.children)
        else:
            yield n

def run():
    app = QApplication(sys.argv)
    app.setApplicationName("jorkXL's Oblivion Remastered Mod Manager")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 