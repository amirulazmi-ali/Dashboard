import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer, QDateTime, Qt
from PyQt6.QtGui import QFont

class LiveClockWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TV Display Live Clock v1.7")
        self.lbl_clock = QLabel()
        self.lbl_clock.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self.lbl_clock.setStyleSheet("color: #38bdf8; background: #0f172a; padding: 20px;")
        self.lbl_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.setCentralWidget(self.lbl_clock)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

    def update_time(self):
        self.lbl_clock.setText(QDateTime.currentDateTime().toString("HH:mm:ss (ddd)"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = LiveClockWindow()
    win.resize(400, 150)
    win.show()
    sys.exit(app.exec())