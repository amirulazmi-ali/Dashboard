import os
import sqlite3
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_name="production_data.db"):
        home_dir = os.path.expanduser("~")
        db_path = os.path.join(home_dir, db_name)
        self.conn = sqlite3.connect(db_path)
        self.create_tables()
        self.migrate_schema()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shift_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, shift TEXT, model TEXT, line TEXT,
                cycle_time REAL, uph INTEGER, leader_name TEXT,
                supervisor_name TEXT, start_time TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_machine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id INTEGER, hour_block TEXT, cumulative_input INTEGER,
                scrap_input INTEGER, hourly_actual INTEGER, delta INTEGER,
                yield_perc REAL, downtime TEXT, remarks TEXT, timestamp TEXT,
                FOREIGN KEY (shift_id) REFERENCES shift_config(id)
            )
        ''')
        self.conn.commit()

    def migrate_schema(self):
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(shift_config)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'start_time' not in columns:
            cursor.execute("ALTER TABLE shift_config ADD COLUMN start_time TEXT")
            self.conn.commit()

    def clear_database(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM raw_machine_logs")
        cursor.execute("DELETE FROM shift_config")
        cursor.execute("DELETE FROM sqlite_sequence")
        self.conn.commit()

    def save_shift_config(self, date, shift, model, line, cycle_time, uph, leader_name, supervisor_name, start_time):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO shift_config (date, shift, model, line, cycle_time, uph, leader_name, supervisor_name, start_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, shift, model, line, cycle_time, uph, leader_name, supervisor_name, start_time))
        self.conn.commit()
        return cursor.lastrowid

    def get_last_active_shift(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, shift, model, line, cycle_time, uph, leader_name, supervisor_name, start_time 
            FROM shift_config ORDER BY id DESC LIMIT 1
        ''')
        return cursor.fetchone()

    def get_all_shift_configs(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, shift, model, line, uph, leader_name, supervisor_name, start_time 
            FROM shift_config ORDER BY id DESC
        ''')
        return cursor.fetchall()

    def get_shift_config_by_id(self, shift_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, date, shift, model, line, cycle_time, uph, leader_name, supervisor_name, start_time 
            FROM shift_config WHERE id = ?
        ''', (shift_id,))
        return cursor.fetchone()

    def get_last_cumulative(self, shift_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT cumulative_input FROM raw_machine_logs 
            WHERE shift_id = ? ORDER BY id DESC LIMIT 1
        ''', (shift_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

    def log_actuals(self, shift_id, hour_block, cumulative_input, scrap, uph, downtime, remarks):
        last_cum = self.get_last_cumulative(shift_id)
        hourly_actual = cumulative_input if cumulative_input < last_cum else cumulative_input - last_cum
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO raw_machine_logs 
            (shift_id, hour_block, cumulative_input, scrap_input, hourly_actual, delta, yield_perc, downtime, remarks, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (shift_id, hour_block, cumulative_input, scrap, hourly_actual, 0, 0.0, downtime, remarks, timestamp))
        self.conn.commit()

    def get_shift_logs(self, shift_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT hour_block, hourly_actual, cumulative_input, scrap_input, downtime, remarks 
            FROM raw_machine_logs WHERE shift_id = ?
        ''', (shift_id,))
        return cursor.fetchall()
