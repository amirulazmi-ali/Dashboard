import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen
from PyQt6.QtCore import Qt

class GroupedBarCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.plans = [300, 300, 300, 300]
        self.actuals = [280, 310, 290, 320]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        slot_w = self.width() / len(self.plans)
        bar_w = slot_w * 0.35

        for i in range(len(self.plans)):
            x_base = i * slot_w + 10
            # Plan Bar (Gold)
            painter.setBrush(QBrush(QColor("#f59e0b")))
            painter.drawRect(int(x_base), 300 - self.plans[i], int(bar_w), self.plans[i])
            # Actual Bar (Green/Red)
            color = QColor("#16a34a") if self.actuals[i] >= self.plans[i] else QColor("#dc2626")
            painter.setBrush(QBrush(color))
            painter.drawRect(int(x_base + bar_w + 5), 300 - self.actuals[i], int(bar_w), self.actuals[i])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = GroupedBarCanvas()
    w.resize(500, 350)
    w.show()
    sys.exit(app.exec())