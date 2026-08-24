import sys
import os
import sqlite3
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, 
                             QMessageBox, QComboBox, QGroupBox, QFormLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QTime
from PyQt6.QtGui import QColor

SHIFT_HOURS = {
    "Day Shift (07:00 - 19:00)": [
        "0700-0800", "0800-0900", "0900-1000", "1000-1100", "1100-1200", 
        "1200-1300", "1300-1400", "1400-1500", "1500-1600", "1600-1700", 
        "1700-1800", "1800-1900"
    ]
}

def format_downtime_display(downtime_str):
    if not downtime_str or downtime_str == "-":
        return "-"
    return downtime_str.strip()

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
                date TEXT, shift TEXT, model TEXT, line TEXT, uph INTEGER, leader_name TEXT, supervisor_name TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_machine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id INTEGER, hour_block TEXT, cumulative_input INTEGER,
                scrap_input INTEGER, hourly_actual INTEGER, downtime TEXT, remarks TEXT, timestamp TEXT
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

    def get_last_cumulative(self, shift_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT cumulative_input FROM raw_machine_logs WHERE shift_id = ? ORDER BY id DESC LIMIT 1', (shift_id,))
        res = cursor.fetchone()
        return res[0] if res else 0

    def log_actuals(self, shift_id, hour_block, cumulative, scrap, downtime, remarks):
        last_cum = self.get_last_cumulative(shift_id)
        hourly_actual = cumulative if cumulative < last_cum else cumulative - last_cum
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO raw_machine_logs (shift_id, hour_block, cumulative_input, scrap_input, hourly_actual, downtime, remarks, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (shift_id, hour_block, cumulative, scrap, hourly_actual, downtime, remarks))
        self.conn.commit()

    def get_shift_logs(self, shift_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT hour_block, hourly_actual, cumulative_input, scrap_input, downtime, remarks FROM raw_machine_logs WHERE shift_id = ?', (shift_id,))
        return cursor.fetchall()

class DashboardWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("Production Dashboard v1.1 - Shift Isolation")
        self.resize(1280, 720)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        self.table = QTableWidget(12, 7)
        self.table.setHorizontalHeaderLabels(["TIME", "PLAN", "ACTUAL", "DELTA", "YIELD (%)", "DOWNTIME", "REMARKS"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def update_dashboard(self, shift_data, logs, hours):
        uph = shift_data[5]
        self.table.setRowCount(len(hours))
        for i, h in enumerate(hours):
            self.table.setItem(i, 0, QTableWidgetItem(h))
            self.table.setItem(i, 1, QTableWidgetItem(str(uph)))
        
        for idx, log in enumerate(logs):
            hour_block, hourly_actual, cumulative, scrap, downtime, remarks = log
            row = hours.index(hour_block) if hour_block in hours else idx
            self.table.setItem(row, 2, QTableWidgetItem(f"{hourly_actual} / {cumulative}"))
            delta = cumulative - (uph * (row + 1))
            self.table.setItem(row, 3, QTableWidgetItem(str(delta)))
            yield_p = ((hourly_actual - scrap) / hourly_actual * 100) if hourly_actual > 0 else 0.0
            self.table.setItem(row, 4, QTableWidgetItem(f"{yield_p:.1f}%"))
            self.table.setItem(row, 5, QTableWidgetItem(format_downtime_display(downtime)))
            self.table.setItem(row, 6, QTableWidgetItem(remarks))

class OperatorWindow(QMainWindow):
    data_updated = pyqtSignal(tuple, list, list)

    def __init__(self, db, dashboard):
        super().__init__()
        self.db = db
        self.dashboard = dashboard
        self.active_shift_id = None
        self.active_hours = SHIFT_HOURS["Day Shift (07:00 - 19:00)"]
        self.setWindowTitle("Operator Kiosk v1.1")
        self.resize(380, 500)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        form = QFormLayout()
        self.uph_input = QLineEdit("300")
        self.start_btn = QPushButton("Start Run")
        self.start_btn.clicked.connect(self.start_run)
        form.addRow("Plan UPH:", self.uph_input)
        form.addRow("", self.start_btn)

        self.hour_combo = QComboBox()
        self.hour_combo.addItems(self.active_hours)
        self.cum_input = QLineEdit()
        self.scrap_input = QLineEdit("0")
        self.save_btn = QPushButton("Save Actuals")
        self.save_btn.clicked.connect(self.save_actuals)

        form.addRow("Hour Slot:", self.hour_combo)
        form.addRow("Cumulative Total:", self.cum_input)
        form.addRow("Scrap:", self.scrap_input)
        form.addRow("", self.save_btn)

        layout.addLayout(form)

    def start_run(self):
        uph = int(self.uph_input.text())
        self.active_shift_id = self.db.save_shift_config("TODAY", "Day", "MODEL1", "L1", uph, "LEADER", "SUPV")
        self.active_shift_data = (self.active_shift_id, "TODAY", "Day", "MODEL1", "L1", uph, "LEADER", "SUPV")
        QMessageBox.information(self, "Success", "Isolated Shift Started")

    def save_actuals(self):
        if self.active_shift_id:
            cum = int(self.cum_input.text())
            scrap = int(self.scrap_input.text())
            slot = self.hour_combo.currentText()
            self.db.log_actuals(self.active_shift_id, slot, cum, scrap, "-", "-")
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