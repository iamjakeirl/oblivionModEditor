# Main window GUI code for Oblivion Remastered Mod Manager
import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt
from mod_manager.utils import get_game_path, SETTINGS_PATH
from mod_manager.registry import list_esp_files, read_plugins_txt, write_plugins_txt
import json

EXAMPLE_PATH = r"C:\Games\OblivionRemastered"  # Example for user reference

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Oblivion Remastered Mod Manager")
        self.resize(600, 400)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

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
        self.save_path_btn = QPushButton("Save Path")
        self.save_path_btn.clicked.connect(self.save_game_path)
        self.path_layout.addWidget(self.save_path_btn)

        # ESP/Plugins controls
        self.esp_label = QLabel(".esp Files in Data Folder:")
        self.layout.addWidget(self.esp_label)
        self.esp_list = QListWidget()
        self.esp_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.layout.addWidget(self.esp_list)

        self.plugins_label = QLabel("Load Order (plugins.txt):")
        self.layout.addWidget(self.plugins_label)
        self.plugins_list = QListWidget()
        self.plugins_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.plugins_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.layout.addWidget(self.plugins_list)

        self.save_plugins_btn = QPushButton("Save Load Order")
        self.save_plugins_btn.clicked.connect(self.save_plugins)
        self.layout.addWidget(self.save_plugins_btn)

        self.deactivate_btn = QPushButton("Deactivate Selected Mod")
        self.deactivate_btn.clicked.connect(self.deactivate_selected)
        self.layout.addWidget(self.deactivate_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_lists)
        self.layout.addWidget(self.refresh_btn)

        self.load_settings()
        self.refresh_lists()

    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Oblivion Remastered Folder")
        if path:
            self.path_input.setText(path)

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
        QMessageBox.information(self, "Saved", "Game path saved.")
        self.refresh_lists()

    def load_settings(self):
        path = get_game_path()
        if path:
            self.path_input.setText(path)

    def refresh_lists(self):
        # ESPs
        self.esp_list.clear()
        esp_files = list_esp_files()
        for esp in esp_files:
            self.esp_list.addItem(esp)
        # Plugins.txt
        self.plugins_list.clear()
        plugins = read_plugins_txt()
        for plugin in plugins:
            item = QListWidgetItem(plugin)
            if plugin.startswith('#'):
                item.setForeground(Qt.gray)
            self.plugins_list.addItem(item)

    def save_plugins(self):
        plugins = []
        for i in range(self.plugins_list.count()):
            plugins.append(self.plugins_list.item(i).text())
        if write_plugins_txt(plugins):
            QMessageBox.information(self, "Saved", "plugins.txt updated.")
        else:
            QMessageBox.warning(self, "Error", "Failed to write plugins.txt.")
        self.refresh_lists()

    def deactivate_selected(self):
        row = self.plugins_list.currentRow()
        if row < 0:
            return
        item = self.plugins_list.item(row)
        text = item.text()
        if not text.startswith('#'):
            item.setText(f'#{text}')
            item.setForeground(Qt.gray)


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 