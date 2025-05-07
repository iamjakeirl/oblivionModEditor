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
    QTableWidget, QTableWidgetItem, QTableView, QTreeView
)
from PyQt5.QtCore import Qt, QEvent, QItemSelectionModel, QUrl, QMimeData, QTimer, QByteArray, QSortFilterProxyModel
from PyQt5.QtGui import QDrag, QPixmap, QColor, QFont, QDragEnterEvent, QDropEvent
from mod_manager.utils import (
    get_game_path, SETTINGS_PATH, get_esp_folder, DATA_DIR, open_folder_in_explorer,
    guess_install_type, set_install_type, load_settings, save_settings,
    get_custom_mod_dir_name, _merge_tree, get_display_info, _display_cache,
)
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
        super().__init__()
        self.setWindowTitle("jorkXL's Oblivion Remastered Mod Manager")
        self.resize(720, 720)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

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

        # Disabled mods list (shows commented or not-in-plugins.txt mods)
        self.disabled_mods_label = QLabel("Disabled Mods (double-click to enable):")
        self.disabled_mods_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.disabled_mods_label.setAlignment(Qt.AlignCenter)
        self.esp_layout.addWidget(self.disabled_mods_label)
        self.disabled_mods_list = QListWidget()
        self.disabled_mods_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.disabled_mods_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.disabled_mods_list.itemDoubleClicked.connect(self.enable_mod)
        self.disabled_mods_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.disabled_mods_list.customContextMenuRequested.connect(self.show_context_menu)
        self.esp_layout.addWidget(self.disabled_mods_list)

        # Create a frame to act as the header bar
        enabled_header = QFrame()
        enabled_header.setFrameShape(QFrame.StyledPanel)
        enabled_header.setFrameShadow(QFrame.Plain)
        enabled_header_layout = QHBoxLayout(enabled_header)
        enabled_header_layout.setContentsMargins(8, 2, 8, 2)
        enabled_header.setStyleSheet("""
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
        checkbox_container.setFixedWidth(150)  # Increased from 120 to 150
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        
        # Checkbox in its container
        self.hide_stock_checkbox = QCheckBox("Hide stock ESPs")
        self.hide_stock_checkbox.setChecked(True)
        self.hide_stock_checkbox.stateChanged.connect(self.refresh_lists)
        checkbox_layout.addWidget(self.hide_stock_checkbox, 0, Qt.AlignRight | Qt.AlignVCenter)

        # Add empty widget with same width as checkbox container for balance
        spacer_widget = QWidget()
        spacer_widget.setFixedWidth(150)  # Increased from 120 to 150

        # Add widgets to main layout
        enabled_header_layout.addWidget(spacer_widget)
        
        # Centered label (no frame/border)
        self.enabled_mods_label = QLabel("Enabled Mods (double-click to disable, drag to reorder):")
        self.enabled_mods_label.setStyleSheet("font-weight: bold; color: #ff9800; border: none; background: transparent;")
        self.enabled_mods_label.setAlignment(Qt.AlignCenter)
        self.enabled_mods_label.setFrameStyle(QFrame.NoFrame)
        enabled_header_layout.addWidget(self.enabled_mods_label, 1, Qt.AlignCenter)

        # Add checkbox container
        enabled_header_layout.addWidget(checkbox_container)

        # Add the header frame to the main layout
        self.esp_layout.addWidget(enabled_header)

        self.enabled_mods_list = PluginsListWidget()
        self.enabled_mods_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.enabled_mods_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.enabled_mods_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.enabled_mods_list.itemDoubleClicked.connect(self.disable_mod)
        self.enabled_mods_list.customContextMenuRequested.connect(self.show_context_menu)
        self.esp_layout.addWidget(self.enabled_mods_list)
        # Set reorder callback
        self.enabled_mods_list.set_reorder_callback(self.update_plugins_txt_from_enabled_list)

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
        self.inactive_pak_view = QTreeView()
        self.pak_layout.insertWidget(3, self.inactive_pak_view)

        # Enabled PAKs label and table
        self.active_pak_label = QLabel("Enabled PAKs (double-click to deactivate):")
        self.active_pak_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.active_pak_label.setAlignment(Qt.AlignCenter)
        self.pak_layout.insertWidget(4, self.active_pak_label)
        self.active_pak_view = QTreeView()
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

        # --- UE4SS TAB ----------------------------------------------------
        self.ue4ss_frame = QWidget()
        self.ue4ss_layout = QVBoxLayout()
        self.ue4ss_frame.setLayout(self.ue4ss_layout)

        # Disabled UE4SS mods list (top)
        self.ue4ss_disabled_label = QLabel("Disabled UE4SS Mods (double-click to enable):")
        self.ue4ss_disabled_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.ue4ss_disabled_label.setAlignment(Qt.AlignCenter)
        self.ue4ss_layout.addWidget(self.ue4ss_disabled_label)
        self.ue4ss_disabled_list = QListWidget()
        self.ue4ss_disabled_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ue4ss_disabled_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ue4ss_disabled_list.itemDoubleClicked.connect(self.enable_ue4ss_mod)
        self.ue4ss_disabled_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ue4ss_disabled_list.customContextMenuRequested.connect(self._show_ue4ss_context_menu)
        self.ue4ss_layout.addWidget(self.ue4ss_disabled_list)

        # Enabled UE4SS mods list (bottom)
        self.ue4ss_enabled_label = QLabel("Enabled UE4SS Mods (double-click to disable):")
        self.ue4ss_enabled_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.ue4ss_enabled_label.setAlignment(Qt.AlignCenter)
        self.ue4ss_layout.addWidget(self.ue4ss_enabled_label)
        self.ue4ss_enabled_list = QListWidget()
        self.ue4ss_enabled_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ue4ss_enabled_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ue4ss_enabled_list.itemDoubleClicked.connect(self.disable_ue4ss_mod)
        self.ue4ss_enabled_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ue4ss_enabled_list.customContextMenuRequested.connect(self._show_ue4ss_context_menu)
        self.ue4ss_layout.addWidget(self.ue4ss_enabled_list)

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
                    
                # Install the extracted files
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
        for root, dirs, files in os.walk(extract_dir):
            if any(f.lower().endswith(".lua") for f in files) and \
               os.path.basename(root).lower() == "scripts":
                mod_root = Path(root).parent  # FolderX
                ue4ss_mod_folders.append(mod_root)
        ue4ss_mod_folders = list({p for p in ue4ss_mod_folders})  # dedupe
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
        # --- End UE4SS mod install ---
        
        # Enable all installed ESPs by adding them to the end of plugins.txt
        if installed_esp_names:
            plugins = read_plugins_txt()
            # Remove any existing entries (commented or uncommented)
            plugins = [p for p in plugins if p.lstrip('#').strip() not in installed_esp_names]
            # Add all ESPs as enabled (uncommented) at the end
            for esp_name in installed_esp_names:
                plugins.append(esp_name)
            write_plugins_txt(plugins)
        
        # Show summary in status bar instead of a popup
        summary = (f"Installed {installed_esp} ESP, {installed_pak} PAK, "
                   f"{installed_ue4ss} UE4SS mod(s) from {mod_name}.")
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

    def load_settings(self):
        self.game_path = get_game_path()
        if self.game_path:
            self.path_input.setText(self.game_path)

    def refresh_lists(self):
        # Get all ESP files from data folder (source of truth for available mods)
        esp_files = list_esp_files()
        mod_esps = [esp for esp in esp_files if esp not in DEFAULT_LOAD_ORDER and esp not in EXCLUDED_ESPS]
        
        # Get plugins.txt content - both enabled and disabled (commented)
        plugins_lines = read_plugins_txt()
        
        # Track enabled and disabled mods
        enabled_mods = []
        disabled_mods = []
        
        # Parse plugins.txt content
        plugins_in_file = set()  # All ESPs mentioned in plugins.txt, commented or not
        for line in plugins_lines:
            name = line.lstrip('#').strip()
            if name in mod_esps:  # Only consider user mods, not default/excluded
                plugins_in_file.add(name)
                if line.startswith('#'):
                    disabled_mods.append(name)
                else:
                    enabled_mods.append(line)
        
        # Add mods that exist in data folder but not in plugins.txt to disabled list
        for esp in mod_esps:
            if esp not in plugins_in_file:
                disabled_mods.append(esp)
        
        # Update disabled mods list
        self.disabled_mods_list.clear()
        for esp in sorted(disabled_mods, key=str.lower):
            self.disabled_mods_list.addItem(esp)
        
        # Update enabled mods list
        self.enabled_mods_list.clear()
        # First add default ESPs unless hidden
        if not self.hide_stock_checkbox.isChecked():
            for esp in DEFAULT_LOAD_ORDER:
                if any(p.lstrip('#').strip() == esp for p in plugins_lines):
                    item = QListWidgetItem(esp)
                    self.enabled_mods_list.addItem(item)
        
        # Then add user-enabled mods
        for plugin in enabled_mods:
            if plugin.lstrip('#').strip() not in DEFAULT_LOAD_ORDER:
                item = QListWidgetItem(plugin)
                self.enabled_mods_list.addItem(item)

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

        # ── 1) DETACH OLD MODELS so Qt never keeps indexes from a dead proxy ──
        for _view in (self.active_pak_view, self.inactive_pak_view):
            _view.setModel(None)

        # ── 2) (Re)build row‑dicts with **display** + **group** information ──
        cache       = _display_cache()                                       # O(1) lookup
        by_filename = {cid.split('|')[-1]: info for cid, info in cache.items()}

        all_rows = []
        for pak in pak_mods:
            subfolder = pak.get('subfolder', '') or ''
            # Normalize subfolder: strip DisabledMods[\/] prefix if present
            import re
            norm_subfolder = re.sub(r'^(DisabledMods[\\/]+)', '', subfolder, flags=re.IGNORECASE)
            norm_mod_id = f"{norm_subfolder}|{pak['name']}"
            orig_mod_id = f"{subfolder}|{pak['name']}"
            # Try normalized mod_id, then original, then by filename
            disp_info = cache.get(norm_mod_id) or cache.get(orig_mod_id) or by_filename.get(pak["name"], {})
            all_rows.append({
                "id":        orig_mod_id,
                "real":      pak["name"],
                "display":   disp_info.get("display", pak["name"]),
                "group":     disp_info.get("group", ""),
                "subfolder": pak.get("subfolder"),
                "active":    pak.get("active", True),
                "pak_info":  pak,
            })
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
        # Models and proxies
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

        self.active_pak_proxy = QSortFilterProxyModel(self)
        self.active_pak_proxy.setSourceModel(self.active_pak_model)
        self.active_pak_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.active_pak_proxy.setFilterKeyColumn(-1)
        self.inactive_pak_proxy = QSortFilterProxyModel(self)
        self.inactive_pak_proxy.setSourceModel(self.inactive_pak_model)
        self.inactive_pak_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.inactive_pak_proxy.setFilterKeyColumn(-1)

        for view, proxy in (
            (self.active_pak_view,   self.active_pak_proxy),
            (self.inactive_pak_view, self.inactive_pak_proxy)):
            view.setModel(proxy)
            view.setHeaderHidden(False)
            view.setRootIsDecorated(True)
            view.expandAll()                        # default expanded; user can collapse
            view.setStyleSheet(tree_stylesheet)     # use the new tree stylesheet
            try:
                view.doubleClicked.disconnect()
            except Exception:
                pass

        # Connect toggles to both models
        self.chk_real.toggled.connect(self.active_pak_model.layoutChanged.emit)
        self.chk_real.toggled.connect(self.inactive_pak_model.layoutChanged.emit)

        # Search box filters both proxies
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
            print("[DEBUG] Cleared previous doubleClicked connection for inactive_pak_view.")
        except Exception:
            print("[DEBUG] No previous doubleClicked connection for inactive_pak_view to clear.")
        self.active_pak_view.doubleClicked.connect(self._deactivate_pak_view_row)
        print("[DEBUG] Connected doubleClicked for active_pak_view.")
        self.inactive_pak_view.doubleClicked.connect(self._activate_pak_view_row)
        print("[DEBUG] Connected doubleClicked for inactive_pak_view.")
        # Context menus
        self.active_pak_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.active_pak_view.customContextMenuRequested.connect(lambda pos: self._show_pak_view_context_menu(pos, enabled=True))
        self.inactive_pak_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.inactive_pak_view.customContextMenuRequested.connect(lambda pos: self._show_pak_view_context_menu(pos, enabled=False))

        # DEBUG: Print cache keys and first 5 disabled row ids
        print("_display_cache keys:", list(cache.keys()))
        print("disabled_rows ids:", [r['id'] for r in disabled_rows][:5])

    def _activate_pak_view_row(self, index):
        # Activate a PAK from the disabled table
        if not index.isValid():
            return
        src_index = self.inactive_pak_proxy.mapToSource(index)
        is_grp, node = self._is_group_index(src_index)
        if is_grp:
            # bulk‑activate all child leaf nodes
            for child in node.children:
                if not child.is_group:
                    activate_pak(self.game_path, child.data["pak_info"])
            self._load_pak_list()
            return
        pak_info = node.data["pak_info"]
        success = activate_pak(self.game_path, pak_info)
        if not success:
            self.show_status(f"Error: Failed to activate PAK mod: {pak_info['name']}", 5000, "error")
        else:
            self.show_status(f"Activated PAK mod: {pak_info['name']}", 3000, "success")
        self._load_pak_list()

    def _deactivate_pak_view_row(self, index):
        # Deactivate a PAK from the enabled table
        if not index.isValid():
            return
        src_index = self.active_pak_proxy.mapToSource(index)
        is_grp, node = self._is_group_index(src_index)
        if is_grp:
            for child in node.children:
                if not child.is_group:
                    deactivate_pak(self.game_path, child.data["pak_info"])
            self._load_pak_list()
            return
        pak_info = node.data["pak_info"]
        success = deactivate_pak(self.game_path, pak_info)
        if not success:
            self.show_status(f"Error: Failed to deactivate PAK mod: {pak_info['name']}", 5000, "error")
        else:
            self.show_status(f"Deactivated PAK mod: {pak_info['name']}", 3000, "success")
        self._load_pak_list()

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
        rename_action = context_menu.addAction("Rename Display Name…")
        group_action  = context_menu.addAction("Set Group…")
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
            from mod_manager.utils import get_display_info, set_display_info
            current_group = get_display_info(mod_id).get("group", "")
            text, ok = QInputDialog.getText(
                self, "Set Group", "Group:", text=current_group
            )
            if not ok:
                return
            set_display_info(mod_id, group=text.strip())
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

    def open_current_tab_folder(self):
        """
        Open the ESP, PAK, or UE4SS directory depending on the selected tab.
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
        elif current_index == 2:  # UE4SS tab
            from mod_manager.ue4ss_installer import get_ue4ss_bin_dir
            ue4ss_folder = get_ue4ss_bin_dir(self.game_path)
            if ue4ss_folder and os.path.isdir(ue4ss_folder):
                open_folder_in_explorer(ue4ss_folder)
            else:
                self.show_status("UE4SS folder not found.", 4000, "error")

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
            self.ue4ss_enabled_list.clear()
            self.ue4ss_disabled_list.clear()
            return
        ok, version = ue4ss_installed(self.game_path)
        enabled, disabled = read_ue4ss_mods_txt(self.game_path)
        # Filter out default/sentinel mods
        default_mods = {
            "CheatManagerEnablerMod", "ConsoleCommandsMod", "ConsoleEnablerMod",
            "SplitScreenMod", "LineTraceMod", "BPML_GenericFunctions", "BPModLoaderMod", "Keybinds"
        }
        sentinel = "; Built-in keybinds, do not move up!"
        enabled = [mod for mod in enabled if mod not in default_mods and mod != sentinel]
        disabled = [mod for mod in disabled if mod not in default_mods and mod != sentinel]
        self.ue4ss_enabled_list.clear()
        self.ue4ss_disabled_list.clear()
        for mod in sorted(enabled, key=str.lower):
            self.ue4ss_enabled_list.addItem(mod)
        for mod in sorted(disabled, key=str.lower):
            self.ue4ss_disabled_list.addItem(mod)
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