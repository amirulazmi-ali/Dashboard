import sys
import os
import sqlite3
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, 
                             QMessageBox, QComboBox, QGroupBox, QFormLayout, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush

HAS_PYQTGRAPH = False
try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

SHIFT_HOURS = {
    "Day Shift (07:00 - 19:00)": [
        "0700-0800", "0800-0900", "0900-1000", "1000-1100", "1100-1200", 
        "1200-1300", "1300-1400", "1400-1500", "1500-1600", "1600-1700", 
        "1700-1800", "1800-1900"
    ]
}

class DatabaseManager:
    def __init__(self, db_name="production_data.db"):
        db_path = os.path.join(os.path.expanduser("~"), db_name)
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shift_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, shift TEXT, model TEXT, line TEXT,
                uph INTEGER, leader_name TEXT, supervisor_name TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_machine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id INTEGER, hour_block TEXT, cumulative_input INTEGER,
                hourly_actual INTEGER, downtime TEXT, remarks TEXT, timestamp TEXT
            )
        ''')
        self.conn.commit()

    def save_shift_config(self, date, shift, model, line, uph, leader, supervisor):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO shift_config (date, shift, model, line, uph, leader_name, supervisor_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, shift, model, line, uph, leader, supervisor))
        self.conn.commit()
        return cursor.lastrowid

    def log_actuals(self, shift_id, hour_block, cumulative, hourly_actual, downtime, remarks):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO raw_machine_logs (shift_id, hour_block, cumulative_input, hourly_actual, downtime, remarks, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (shift_id, hour_block, cumulative, hourly_actual, downtime, remarks))
        self.conn.commit()

    def get_shift_logs(self, shift_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT hour_block, hourly_actual, cumulative_input, downtime, remarks FROM raw_machine_logs WHERE shift_id = ?', (shift_id,))
        return cursor.fetchall()

class DashboardWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("Production Dashboard v1.0")
        self.resize(1280, 720)
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)
        
        self.table = QTableWidget(12, 5)
        self.table.setHorizontalHeaderLabels(["TIME", "PLAN", "ACTUAL", "DOWNTIME", "REMARKS"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.table)

    def update_dashboard(self, shift_data, logs, hours):
        self.table.setRowCount(len(hours))
        for i, h in enumerate(hours):
            self.table.setItem(i, 0, QTableWidgetItem(h))
            self.table.setItem(i, 1, QTableWidgetItem(str(shift_data[5])))
        for idx, log in enumerate(logs):
            row = hours.index(log[0]) if log[0] in hours else idx
            self.table.setItem(row, 2, QTableWidgetItem(str(log[1])))
            self.table.setItem(row, 3, QTableWidgetItem(str(log[3])))
            self.table.setItem(row, 4, QTableWidgetItem(str(log[4])))

class OperatorWindow(QMainWindow):
    data_updated = pyqtSignal(tuple, list, list)

    def __init__(self, db, dashboard):
        super().__init__()
        self.db = db
        self.dashboard = dashboard
        self.active_shift_id = None
        self.active_hours = SHIFT_HOURS["Day Shift (07:00 - 19:00)"]
        self.setWindowTitle("Operator Kiosk v1.0")
        self.resize(380, 500)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        form = QFormLayout()
        self.uph_input = QLineEdit()
        self.start_btn = QPushButton("Start Run")
        self.start_btn.clicked.connect(self.start_run)
        form.addRow("Plan UPH:", self.uph_input)
        form.addRow("", self.start_btn)

        self.cum_input = QLineEdit()
        self.save_btn = QPushButton("Save Actuals")
        self.save_btn.clicked.connect(self.save_actuals)
        form.addRow("Cumulative Total:", self.cum_input)
        form.addRow("", self.save_btn)

        layout.addLayout(form)

    def start_run(self):
        try:
            uph = int(self.uph_input.text())
            self.active_shift_id = self.db.save_shift_config("TODAY", "Day", "MODEL1", "L1", uph, "LEADER", "SUPV")
            self.active_shift_data = (self.active_shift_id, "TODAY", "Day", "MODEL1", "L1", uph, "LEADER", "SUPV")
            QMessageBox.information(self, "Success", "Run Started")
        except ValueError:
            pass

    def save_actuals(self):
        if self.active_shift_id:
            cum = int(self.cum_input.text())
            self.db.log_actuals(self.active_shift_id, self.active_hours[0], cum, cum, "-", "-")
            logs = self.db.get_shift_logs(self.active_shift_id)
            self.data_updated.emit(self.active_shift_data, logs, self.active_hours)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    db = DatabaseManager()
    dash = DashboardWindow(db)
    op = OperatorWindow(db, dash)
    op.data_updated.connect(dash.update_dashboard)
    dash.show()
    op.show()
    sys.exit(app.exec())