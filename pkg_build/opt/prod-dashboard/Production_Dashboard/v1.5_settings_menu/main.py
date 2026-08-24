import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt6.QtGui import QAction, QActionGroup

class MenuWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kiosk Menu Bar Settings v1.5")
        self.setCentralWidget(QLabel("Check Settings menu above", alignment=Qt.AlignmentFlag.AlignCenter))
        
        menu = self.menuBar().addMenu("Settings")
        flip_menu = menu.addMenu("Auto-Flip Timing")
        
        group = QActionGroup(self)
        for label in ["Off", "10 Seconds", "30 Seconds", "60 Seconds"]:
            act = QAction(label, self, checkable=True)
            group.addAction(act)
            flip_menu.addAction(act)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MenuWindow()
    win.resize(400, 200)
    win.show()
    sys.exit(app.exec())