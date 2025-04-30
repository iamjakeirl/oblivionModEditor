# Main window GUI code for Oblivion Remastered Mod Manager
import sys
import os
import shutil
import tempfile
import uuid
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QAbstractItemView, QCheckBox,
    QMenu, QAction, QTabWidget, QInputDialog, QProgressDialog, QFrame
)
from PyQt5.QtCore import Qt, QEvent, QItemSelectionModel, QUrl, QMimeData, QTimer
from PyQt5.QtGui import QDrag, QPixmap, QColor, QFont, QDragEnterEvent, QDropEvent
from mod_manager.utils import get_game_path, SETTINGS_PATH, get_esp_folder, DATA_DIR
from mod_manager.registry import list_esp_files, read_plugins_txt, write_plugins_txt
from mod_manager.pak_manager import (
    list_managed_paks, add_pak, remove_pak, scan_for_installed_paks, 
    reconcile_pak_list, PAK_EXTENSION, RELATED_EXTENSIONS, create_subfolder,
    activate_pak, deactivate_pak, get_pak_target_dir
)
import json

# Import archive handling libraries
import zipfile
import py7zr
import rarfile
from pyunpack import Archive

# Note: rarfile library requires unrar executable to be installed on the system or in PATH
# If not available, we'll fall back to pyunpack which uses whatever extractor is available
# See: https://rarfile.readthedocs.io/en/latest/

EXAMPLE_PATH = r"C:\Games\OblivionRemastered"  # Example for user reference

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
        self.drag_drop_label = QLabel("Tip: You can drag and drop .zip, .7z, or .rar archives onto this window to install mods")
        self.drag_drop_label.setStyleSheet("color: #888888; font-style: italic;")
        self.drag_drop_label.setAlignment(Qt.AlignCenter)
        self.drag_drop_layout.addWidget(self.drag_drop_label)

        # Store the game path for later use
        self.game_path = get_game_path()

        # Create tab widget
        self.notebook = QTabWidget()
        self.layout.addWidget(self.notebook)

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

        # Enabled mods list (from plugins.txt, uncommented only)
        enabled_header = QWidget()
        enabled_header_layout = QHBoxLayout(enabled_header)
        enabled_header_layout.setContentsMargins(0, 4, 0, 4)
        
        # Add a spacer on the left to balance with checkbox width
        enabled_header_layout.addStretch(1)
        
        # Add the centered label
        self.enabled_mods_label = QLabel("Enabled Mods (double-click to disable, drag to reorder):")
        self.enabled_mods_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        enabled_header_layout.addWidget(self.enabled_mods_label, 10)
        
        # Add the checkbox and ensure it's properly aligned
        self.hide_stock_checkbox = QCheckBox("Hide stock ESPs")
        self.hide_stock_checkbox.setChecked(True)
        self.hide_stock_checkbox.stateChanged.connect(self.refresh_lists)
        enabled_header_layout.addWidget(self.hide_stock_checkbox, 0, Qt.AlignRight)
        
        # Add a spacer on the right to balance with left spacer
        enabled_header_layout.addStretch(1)
        
        # Add the header to the main layout
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
        
        # Inactive PAK mods list
        self.inactive_pak_label = QLabel("Inactive PAKs (double-click to activate):")
        self.inactive_pak_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.inactive_pak_label.setAlignment(Qt.AlignCenter)
        self.pak_layout.addWidget(self.inactive_pak_label)
        
        self.inactive_pak_listbox = QListWidget()
        self.inactive_pak_listbox.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.inactive_pak_listbox.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inactive_pak_listbox.setContextMenuPolicy(Qt.CustomContextMenu)
        self.inactive_pak_listbox.customContextMenuRequested.connect(self._show_pak_context_menu)
        self.inactive_pak_listbox.itemDoubleClicked.connect(self._activate_pak_double_clicked)
        self.pak_layout.addWidget(self.inactive_pak_listbox)
        
        # Active PAK mods list
        self.active_pak_label = QLabel("Active PAKs (double-click to deactivate):")
        self.active_pak_label.setStyleSheet("font-weight: bold; color: #ff9800;")
        self.active_pak_label.setAlignment(Qt.AlignCenter)
        self.pak_layout.addWidget(self.active_pak_label)
        
        self.active_pak_listbox = QListWidget()
        self.active_pak_listbox.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.active_pak_listbox.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.active_pak_listbox.setContextMenuPolicy(Qt.CustomContextMenu)
        self.active_pak_listbox.customContextMenuRequested.connect(self._show_pak_context_menu)
        self.active_pak_listbox.itemDoubleClicked.connect(self._deactivate_pak_double_clicked)
        self.pak_layout.addWidget(self.active_pak_listbox)
        
        # PAK control buttons
        self.pak_button_row = QHBoxLayout()
        
        self.add_pak_btn = QPushButton("Add PAK...")
        self.add_pak_btn.setMinimumHeight(48)
        self.add_pak_btn.setMinimumWidth(48)
        self.add_pak_btn.clicked.connect(self._add_pak_clicked)
        self.pak_button_row.addWidget(self.add_pak_btn)
        
        self.remove_pak_btn = QPushButton("Remove Selected PAK")
        self.remove_pak_btn.setMinimumHeight(48)
        self.remove_pak_btn.setMinimumWidth(48)
        self.remove_pak_btn.clicked.connect(self._remove_pak_clicked)
        self.pak_button_row.addWidget(self.remove_pak_btn)
        
        self.refresh_pak_btn = QPushButton("Refresh PAK List")
        self.refresh_pak_btn.setMinimumHeight(48)
        self.refresh_pak_btn.setMinimumWidth(48)
        self.refresh_pak_btn.clicked.connect(self._load_pak_list)
        self.pak_button_row.addWidget(self.refresh_pak_btn)
        
        self.pak_layout.addLayout(self.pak_button_row)
        
        # Add PAK tab to notebook
        self.notebook.addTab(self.pak_frame, "PAK Mods")

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
        """)

    # Add drag and drop event handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events for archive files."""
        # Check if the drag contains URLs/files
        if event.mimeData().hasUrls():
            # Check if any URL is a supported archive format
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_supported_archive(file_path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop events for archive files."""
        # Get the URLs from the event
        urls = event.mimeData().urls()
        files_to_process = []
        
        # Filter for supported archive files
        for url in urls:
            file_path = url.toLocalFile()
            if self._is_supported_archive(file_path):
                files_to_process.append(file_path)
        
        # Process the dropped archives
        if files_to_process:
            event.acceptProposedAction()
            self._process_dropped_archives(files_to_process)
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

    def _install_extracted_mod(self, extract_dir, mod_name):
        """
        Install extracted mod files to the appropriate locations.
        
        Args:
            extract_dir: Directory containing extracted mod files
            mod_name: Name of the mod (for display purposes)
        """
        # Find ESP and PAK files in the extracted content
        esp_files = []
        pak_files = []
        
        # Walk through all files in the extracted directory
        for root, _, files in os.walk(extract_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Check if it's an ESP file
                if filename.lower().endswith('.esp'):
                    esp_files.append(filepath)
                
                # Check if it's a PAK file
                elif filename.lower().endswith(PAK_EXTENSION):
                    pak_files.append(filepath)
        
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
                
        # Process PAK files
        installed_pak = 0
        for pak_path in pak_files:
            try:
                # Determine subfolder based on mod structure
                subfolder = None
                
                # If there are multiple PAK files, use mod name as subfolder
                if len(pak_files) > 1:
                    subfolder = mod_name.split('.')[0]  # Use archive name without extension
                
                # Add the PAK file using existing functionality
                result = add_pak(self.game_path, pak_path, subfolder)
                if result:
                    installed_pak += 1
                    
            except Exception as e:
                error_msg = f"Failed to install {os.path.basename(pak_path)}: {str(e)}"
                self.show_status(f"Error: {error_msg}", 10000, "error")
        
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
        summary = f"Installed {installed_esp} ESP file(s) and {installed_pak} PAK file(s) from {mod_name}."
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
        """Load the list of managed PAK mods into the listboxes."""
        self.active_pak_listbox.clear()
        self.inactive_pak_listbox.clear()
        
        # Check if game path is set
        if not self.game_path:
            return
            
        # Reconcile managed PAKs with installed PAKs
        reconcile_pak_list(self.game_path)
        
        # Get the list of managed PAKs
        pak_mods = list_managed_paks()
        
        # Add each PAK to the appropriate listbox based on active status
        for pak_info in pak_mods:
            pak_name = pak_info.get("name", "Unknown PAK")
            
            # Create display name with subfolder if applicable
            display_name = pak_name
            if pak_info.get("subfolder"):
                display_name = f"{pak_info['subfolder']} / {pak_name}"
                
            # Create an item with the PAK name
            item = QListWidgetItem(display_name)
            
            # Store the original pak_info data in the item for later use
            item.setData(Qt.UserRole, pak_info)
            
            # Add file extensions as tooltip if available
            tooltip = ""
            if pak_info.get("subfolder"):
                tooltip += f"Subfolder: {pak_info['subfolder']}\n"
                
            tooltip += f"Status: {'Active' if pak_info.get('active', True) else 'Inactive'}\n"
                
            if "extensions" in pak_info and pak_info["extensions"]:
                extensions_str = ", ".join(pak_info["extensions"])
                tooltip += f"File types: {extensions_str}"
                
                # Add file list if available
                if "files" in pak_info and pak_info["files"]:
                    file_list = "\n".join(os.path.basename(f) for f in pak_info["files"])
                    tooltip += f"\n\nFiles:\n{file_list}"
                
            if tooltip:
                item.setToolTip(tooltip)
                
            # Add to the appropriate listbox based on active status
            if pak_info.get("active", True):
                self.active_pak_listbox.addItem(item)
            else:
                self.inactive_pak_listbox.addItem(item)

    def _activate_pak_double_clicked(self, item):
        """Handle double-click on inactive PAK to activate it."""
        pak_info = item.data(Qt.UserRole)
        if pak_info:
            success = activate_pak(self.game_path, pak_info)
            if not success:
                self.show_status(f"Error: Failed to activate PAK mod: {pak_info['name']}", 5000, "error")
            else:
                self.show_status(f"Activated PAK mod: {pak_info['name']}", 3000, "success")
            self._load_pak_list()

    def _deactivate_pak_double_clicked(self, item):
        """Handle double-click on active PAK to deactivate it."""
        pak_info = item.data(Qt.UserRole)
        if pak_info:
            success = deactivate_pak(self.game_path, pak_info)
            if not success:
                self.show_status(f"Error: Failed to deactivate PAK mod: {pak_info['name']}", 5000, "error")
            else:
                self.show_status(f"Deactivated PAK mod: {pak_info['name']}", 3000, "success")
            self._load_pak_list()

    def _show_pak_context_menu(self, position):
        """Show context menu for PAK mods."""
        # Determine which list widget triggered the context menu
        sender = self.sender()
        
        # Get selected items
        if sender == self.inactive_pak_listbox:
            selected_items = self.inactive_pak_listbox.selectedItems()
            is_active = False
        else:  # sender == self.active_pak_listbox
            selected_items = self.active_pak_listbox.selectedItems()
            is_active = True
            
        if not selected_items:
            return
            
        # Create context menu
        context_menu = QMenu(self)
        
        # Get PAK info for the currently selected item
        current_item = sender.itemAt(position)
        if not current_item:
            current_item = selected_items[0]
            
        pak_info = current_item.data(Qt.UserRole)
        if not pak_info:
            return
            
        # Add actions based on PAK status
        if is_active:
            deactivate_action = QAction("Deactivate PAK", self)
            deactivate_action.triggered.connect(lambda: self._context_deactivate_pak(pak_info))
            context_menu.addAction(deactivate_action)
        else:
            activate_action = QAction("Activate PAK", self)
            activate_action.triggered.connect(lambda: self._context_activate_pak(pak_info))
            context_menu.addAction(activate_action)
            
        # Always add remove action
        remove_action = QAction("Remove PAK", self)
        remove_action.triggered.connect(lambda: self._context_remove_pak(pak_info))
        context_menu.addAction(remove_action)
        
        # Show context menu
        context_menu.exec_(sender.mapToGlobal(position))
    
    def _context_activate_pak(self, pak_info):
        """Activate a PAK mod from context menu."""
        if not self.game_path:
            self.show_status("Error: Game path not set.", 5000, "error")
            return
            
        # Store info for reselection
        to_reselect = [{
            "name": pak_info["name"],
            "subfolder": pak_info.get("subfolder"),
            "active": True  # Will be active after operation
        }]
            
        success = activate_pak(self.game_path, pak_info)
        if success:
            self.show_status(f"Activated PAK mod: {pak_info['name']}", 3000, "success")
            self._load_pak_list()
            self._reselect_items_by_info(to_reselect)
        else:
            self.show_status(f"Error: Failed to activate PAK mod: {pak_info['name']}", 5000, "error")
    
    def _context_deactivate_pak(self, pak_info):
        """Deactivate a PAK mod from context menu."""
        if not self.game_path:
            self.show_status("Error: Game path not set.", 5000, "error")
            return
            
        # Store info for reselection
        to_reselect = [{
            "name": pak_info["name"],
            "subfolder": pak_info.get("subfolder"),
            "active": False  # Will be inactive after operation
        }]
            
        success = deactivate_pak(self.game_path, pak_info)
        if success:
            self.show_status(f"Deactivated PAK mod: {pak_info['name']}", 3000, "success")
            self._load_pak_list()
            self._reselect_items_by_info(to_reselect)
        else:
            self.show_status(f"Error: Failed to deactivate PAK mod: {pak_info['name']}", 5000, "error")
    
    def _context_remove_pak(self, pak_info):
        """Remove a PAK mod from context menu."""
        if not self.game_path:
            QMessageBox.warning(self, "Error", "Game path not set.")
            return
            
        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove PAK mod {pak_info['name']}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        success = remove_pak(self.game_path, pak_info["name"])
        if success:
            self._load_pak_list()
            # No reselection needed for removal since the item is gone
        else:
            QMessageBox.warning(self, "Error", f"Failed to remove PAK mod: {pak_info['name']}")

    def _remove_pak_clicked(self):
        """Handle Remove PAK button click."""
        # Get selected items from both active and inactive lists
        active_selected = self.active_pak_listbox.selectedItems()
        inactive_selected = self.inactive_pak_listbox.selectedItems()
        
        # Combine the selections
        selected_items = active_selected + inactive_selected
        
        # Check if any items are selected
        if not selected_items:
            self.show_status("No PAK files selected for removal.", 4000, "warning")
            return
            
        # Check if game path is set
        if not self.game_path:
            self.show_status("Game path not set. Please set a valid game path first.", 6000, "error")
            return
            
        # Get the original pak info for each selected item
        selected_paks = []
        for item in selected_items:
            pak_info = item.data(Qt.UserRole)
            if pak_info and "name" in pak_info:
                selected_paks.append(pak_info)
        
        if not selected_paks:
            self.show_status("Could not retrieve PAK information for selected items.", 6000, "error")
            return
            
        # Create description list for confirmation message
        pak_descriptions = []
        for pak in selected_paks:
            if pak.get("subfolder"):
                pak_descriptions.append(f"{pak['name']} (in subfolder {pak['subfolder']})")
            else:
                pak_descriptions.append(pak['name'])
        
        # Confirm removal
        confirmation_msg = (
            f"Are you sure you want to remove the following PAK mod(s)?\n\n"
            f"{chr(10).join(pak_descriptions)}\n\n"
            f"This will remove the PAK file and any related files with the same name."
        )
        
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            confirmation_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        # Remove the PAKs
        success_count = 0
        fail_count = 0
        
        for pak in selected_paks:
            if remove_pak(self.game_path, pak["name"]):
                success_count += 1
            else:
                fail_count += 1
                
        # Show results
        result_msg = f"Removed {success_count} PAK mod(s)."
        if fail_count > 0:
            result_msg += f"\nFailed to remove {fail_count} PAK mod(s)."
            
        if fail_count > 0:
            self.show_status(result_msg, 7000, "warning")
        else:
            self.show_status(result_msg, 4000, "success")
            
        # Refresh the list
        self._load_pak_list()

    def _add_pak_clicked(self):
        """Handle Add PAK button click."""
        if not self.game_path:
            self.show_status("Game path not set. Please set a valid game path first.", 6000, "error")
            return
            
        # Show a dialog to choose between adding to root or subfolder
        options = ["Add to root directory", "Add to existing subfolder", "Create new subfolder"]
        choice, ok = QInputDialog.getItem(
            self, 
            "Select Installation Method", 
            "How would you like to install the PAK mod?",
            options,
            0,  # Default to root directory
            False  # Not editable
        )
        
        if not ok:
            return
            
        # Determine the target subfolder based on user choice
        target_subfolder = None
        if choice == "Add to existing subfolder":
            # Scan for existing subfolders
            target_dir = os.path.join(self.game_path, "Content/OblivionRemastered/Content/Paks/~mods")
            if not os.path.exists(target_dir):
                self.show_status("PAK mods directory not found.", 6000, "error")
                return
                
            # Get subfolders
            subfolders = [d for d in os.listdir(target_dir) 
                        if os.path.isdir(os.path.join(target_dir, d))]
            
            if not subfolders:
                self.show_status("No existing subfolders found. Creating a new one instead.", 5000, "warning")
                choice = "Create new subfolder"
            else:
                subfolder, ok = QInputDialog.getItem(
                    self,
                    "Select Subfolder",
                    "Choose a subfolder to install the PAK mod:",
                    sorted(subfolders),
                    0,
                    False
                )
                
                if not ok:
                    return
                    
                target_subfolder = subfolder
                
        if choice == "Create new subfolder":
            subfolder_name, ok = QInputDialog.getText(
                self,
                "Create Subfolder",
                "Enter name for the new subfolder:",
            )
            
            if not ok or not subfolder_name:
                return
                
            # Create the subfolder
            subfolder_path = create_subfolder(self.game_path, subfolder_name)
            if not subfolder_path:
                self.show_status(f"Failed to create subfolder: {subfolder_name}", 6000, "error")
                return
                
            target_subfolder = subfolder_name
            
        # Open file dialog - only allow .pak files for selection
        file_filter = f"PAK Files (*{PAK_EXTENSION});;All Files (*.*)"
        
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select PAK Mod File",
            "",
            file_filter
        )
        
        if selected_file:
            # Validate the file extension
            if not selected_file.lower().endswith(PAK_EXTENSION):
                self.show_status(f"The selected file must be a {PAK_EXTENSION} file. Please select a valid PAK file.", 6000, "error")
                return
                
            # Show information about PAK files
            extensions = [PAK_EXTENSION] + RELATED_EXTENSIONS
            subfolder_info = f" in subfolder '{target_subfolder}'" if target_subfolder else ""
            QMessageBox.information(
                self, 
                "PAK Mod Import", 
                f"The manager will import the selected {PAK_EXTENSION} file and "
                f"look for any related files with the same name but different extensions "
                f"({', '.join(extensions)}).\n\n"
                f"Files will be installed{subfolder_info}."
            )
            
            # Try to add the PAK
            success = add_pak(self.game_path, selected_file, target_subfolder)
            
            if success:
                subfolder_msg = f" to subfolder '{target_subfolder}'" if target_subfolder else ""
                self.show_status(f"Added PAK mod: {os.path.basename(selected_file)}{subfolder_msg}", 4000, "success")
                self._load_pak_list()
            else:
                self.show_status("Failed to add PAK mod. Make sure the selected file is a valid PAK mod file.", 6000, "error")

    def show_settings_location(self):
        """Show the user where settings are stored and provide a summary of features and usage (formatted)."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Settings & Features")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(f"""
        <div style='min-width:420px;'>
        <b>Settings Location</b><br>
        <span style='color:#444;'>{DATA_DIR}</span><br><br>
        This includes game path and mod configurations.<br><hr>
        <b>jorkXL's Oblivion Remastered Mod Manager Features</b><br>
        <ul style='margin-left: -20px;'>
        <li>Drag-and-drop mod import (<b>.zip</b>, <b>.7z</b>, <b>.rar</b>) directly onto the window</li>
        <li>ESP (plugin) and PAK (archive) mod management in separate tabs</li>
        <li>Enable/disable ESP mods and reorder their load order (drag to reorder)</li>
        <li>Hide or show stock ESPs; when hidden, they always load first in default order</li>
        <li>PAK mods can be activated, deactivated, or organized into subfolders</li>
        <li>All changes to load order are saved to <b>Plugins.txt</b> automatically</li>
        <li>Settings and mod registry are portable and stored in the above folder</li>
        <li>Double-click mods to enable/disable or activate/deactivate</li>
        <li>Right-click mods for more options (delete, move, etc.)</li>
        <li>Game path can be set or changed at any time</li>
        <li>Status messages appear at the bottom for feedback</li>
        </ul>
        <b>Tips:</b>
        <ul style='margin-left: -20px;'>
        <li>Always set your game path before installing mods.</li>
        <li>Use the <b>Refresh</b> button if you make changes outside the manager.</li>
        <li>Backups are recommended before making major changes.</li>
        </ul>
        </div>
        """)
        msg.setIcon(QMessageBox.NoIcon)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setMinimumWidth(500)
        msg.exec_()

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

def run():
    app = QApplication(sys.argv)
    app.setApplicationName("jorkXL's Oblivion Remastered Mod Manager")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 