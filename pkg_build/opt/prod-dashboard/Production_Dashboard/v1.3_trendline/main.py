import sys
import os
import sqlite3
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtCore import Qt

def calculate_trend_line(actuals_list):
    valid_points = [(i, val) for i, val in enumerate(actuals_list) if val > 0]
    if len(valid_points) < 2:
        return actuals_list
    n = len(valid_points)
    sum_x = sum(p[0] for p in valid_points)
    sum_y = sum(p[1] for p in valid_points)
    sum_xy = sum(p[0] * p[1] for p in valid_points)
    sum_x2 = sum(p[0] ** 2 for p in valid_points)
    denom = (n * sum_x2 - sum_x ** 2)
    slope = (n * sum_xy - sum_x * sum_y) / denom if denom != 0 else 0
    intercept = (sum_y - slope * sum_x) / n
    return [slope * i + intercept for i in range(len(actuals_list))]

class TrendCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.actuals = [280, 310, 290, 340, 330, 360]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        trend = calculate_trend_line(self.actuals)
        painter.setPen(QPen(QColor("#38bdf8"), 3))
        w = self.width() / len(self.actuals)
        for i in range(len(trend) - 1):
            painter.drawLine(int(i * w + 20), int(400 - trend[i]), int((i + 1) * w + 20), int(400 - trend[i + 1]))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setCentralWidget(TrendCanvas())
        self.resize(600, 450)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())