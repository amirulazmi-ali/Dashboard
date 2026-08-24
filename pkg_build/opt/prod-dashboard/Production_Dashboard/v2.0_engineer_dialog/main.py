import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QDialog, QFormLayout, QLineEdit, QPushButton, QMessageBox
from PyQt6.QtGui import QAction, QKeySequence

class EngineerSetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File -> New Shift Run")
        form = QFormLayout(self)
        self.uph_input = QLineEdit()
        btn = QPushButton("Start Run")
        btn.clicked.connect(self.accept)
        form.addRow("UPH Target:", self.uph_input)
        form.addRow("", btn)

class OperatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Operator Kiosk v2.0")
        menu = self.menuBar().addMenu("File")
        new_act = QAction("New Shift Run", self)
        new_act.setShortcut(QKeySequence("Ctrl+N"))
        new_act.triggered.connect(self.open_setup)
        menu.addAction(new_act)

    def open_setup(self):
        dlg = EngineerSetupDialog()
        if dlg.exec():
            QMessageBox.information(self, "Success", "New Run Initialized!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OperatorWindow()
    win.resize(380, 300)
    win.show()
    sys.exit(app.exec())