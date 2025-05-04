# ui/install_type_dialog.py
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QPushButton, QLabel
from PyQt5.QtCore import Qt

class InstallTypeDialog(QDialog):
    def __init__(self, default_choice: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Install Type")
        self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self)

        self.lbl = QLabel("Choose your Oblivion Remastered installation type:")
        layout.addWidget(self.lbl)

        self.steam_btn = QRadioButton("Steam")
        self.gp_btn = QRadioButton("Game\u202FPass")
        layout.addWidget(self.steam_btn)
        layout.addWidget(self.gp_btn)

        (self.steam_btn if default_choice == "steam" else self.gp_btn).setChecked(True)

        self.ok = QPushButton("OK")
        self.ok.setStyleSheet("border:2px solid #0f0;")  # green outline
        self.ok.clicked.connect(self.accept)
        layout.addWidget(self.ok)

    def selected(self):
        return "steam" if self.steam_btn.isChecked() else "gamepass" 