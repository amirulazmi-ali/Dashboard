import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen

class ProgressiveLegendCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.plans = [300, 300, 300, 300]
        self.actuals = [280, 320, 0, 0]
        self.logged_mask = [True, True, False, False]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        
        # Draw only logged bars
        for i in range(len(self.plans)):
            if self.logged_mask[i]:
                painter.setBrush(QBrush(QColor("#f59e0b")))
                painter.drawRect(i * 80 + 20, 200 - self.plans[i] // 2, 25, self.plans[i] // 2)

        # Draw Legend Box
        painter.setBrush(QBrush(QColor("#1e293b")))
        painter.drawRoundedRect(300, 10, 160, 60, 5, 5)
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(310, 30, "Legend: Progress")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ProgressiveLegendCanvas()
    w.resize(500, 250)
    w.show()
    sys.exit(app.exec())