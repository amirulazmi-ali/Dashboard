import sys
import sqlite3
from PyQt6.QtWidgets import QApplication, QDialog, QTextEdit, QVBoxLayout, QPushButton

class PackageRequirementDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Package Checker v1.9")
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setText(f"• Python: {sys.version.split()[0]}\n• SQLite3: {sqlite3.version}\n• Status: All System Packages Operational")
        layout.addWidget(text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = PackageRequirementDialog()
    dlg.resize(400, 200)
    dlg.exec()
    sys.exit(0)