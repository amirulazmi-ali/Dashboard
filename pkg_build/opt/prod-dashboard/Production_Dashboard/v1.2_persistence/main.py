import sys
import os
import sqlite3
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox)
from PyQt6.QtCore import pyqtSignal

class DatabaseManager:
    def __init__(self, db_name="production_data.db"):
        db_path = os.path.join(os.path.expanduser("~"), db_name)
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shift_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, shift TEXT, model TEXT, line TEXT, uph INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_machine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER, hour_block TEXT, cumulative_input INTEGER
            )
        ''')
        self.conn.commit()

    def get_last_active_shift(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, date, shift, model, line, uph FROM shift_config ORDER BY id DESC LIMIT 1')
        return cursor.fetchone()

    def save_shift_config(self, date, shift, model, line, uph):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO shift_config (date, shift, model, line, uph) VALUES (?, ?, ?, ?, ?)', (date, shift, model, line, uph))
        self.conn.commit()
        return cursor.lastrowid

if __name__ == "__main__":
    app = QApplication(sys.argv)
    db = DatabaseManager()
    last = db.get_last_active_shift()
    if last:
        print(f"Restored session ID: {last[0]}")
    else:
        print("No active session found.")
    sys.exit(0)