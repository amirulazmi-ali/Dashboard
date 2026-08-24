import sys
import os
import csv
import signal
import subprocess
import sqlite3
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, 
                             QMessageBox, QComboBox, QGroupBox, QFormLayout,
                             QGridLayout, QStackedWidget, QFileDialog, QDialog, 
                             QListWidget, QListWidgetItem, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTime, QTimer, QDateTime
from PyQt6.QtGui import QColor, QFont, QAction, QActionGroup, QPainter, QPen, QBrush, QKeySequence

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
    ],
    "Night Shift (19:00 - 07:00)": [
        "1900-2000", "2000-2100", "2100-2200", "2200-2300", "2300-0000", 
        "0000-0100", "0100-0200", "0200-0300", "0300-0400", "0400-0500", 
        "0500-0600", "0600-0700"
    ]
}

def kill_previous_instances():
    current_pid = os.getpid()
    try:
        output = subprocess.check_output(["pgrep", "-f", "main.py"]).decode().split()
        for pid_str in output:
            pid = int(pid_str)
            if pid != current_pid:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
    except subprocess.CalledProcessError:
        pass

def format_duration_str(mins):
    if mins >= 60:
        hrs = mins // 60
        m = mins % 60
        return f"{hrs}h {m}m" if m > 0 else f"{hrs}h"
    return f"{mins}m"

def format_downtime_display(downtime_str):
    if not downtime_str or not downtime_str.strip() or downtime_str.strip() == "-":
        return "-"
    text = downtime_str.strip()
    if "-" in text:
        try:
            parts = text.split("-")
            t1 = datetime.strptime(parts[0].strip(), "%H:%M")
            t2 = datetime.strptime(parts[1].strip(), "%H:%M")
            if t2 <= t1:
                t2 += timedelta(days=1)
            duration_mins = int((t2 - t1).total_seconds() // 60)
            return f"{text} ({format_duration_str(duration_mins)})"
        except ValueError:
            pass
    return text

def split_downtime_picker(start_qtime, end_qtime, start_slot, active_hours):
    h1, m1 = start_qtime.hour(), start_qtime.minute()
    h2, m2 = end_qtime.hour(), end_qtime.minute()
    
    start_dt = datetime(2026, 1, 1, h1, m1)
    end_dt = datetime(2026, 1, 1, h2, m2)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
        
    start_idx = active_hours.index(start_slot) if start_slot in active_hours else 0
    results = []
    curr_dt = start_dt

    for i in range(start_idx, len(active_hours)):
        if curr_dt >= end_dt:
            break
        slot_name = active_hours[i]
        s_end_h = int(slot_name[5:7])
        slot_end_dt = datetime(2026, 1, 1, s_end_h, 0)
        if s_end_h == 0 or s_end_h < int(slot_name[:2]):
            slot_end_dt += timedelta(days=1)
        chunk_end = min(end_dt, slot_end_dt)
        chunk_mins = int((chunk_end - curr_dt).total_seconds() // 60)
        if chunk_mins > 0:
            chunk_str = f"{curr_dt.strftime('%H:%M')}-{chunk_end.strftime('%H:%M')}"
            results.append((slot_name, chunk_str))
        curr_dt = chunk_end

    return results if results else [(start_slot, f"{start_qtime.toString('HH:mm')}-{end_qtime.toString('HH:mm')}")]

def calculate_plan_targets(active_hours, full_uph, start_time_str):
    try:
        sh, sm = map(int, start_time_str.split(":"))
    except (ValueError, AttributeError):
        sh, sm = 7, 0

    start_mins_total = sh * 60 + sm
    plan_list = []
    cum_plan_list = []
    running_cum = 0

    for slot in active_hours:
        s_start_h = int(slot[:2])
        s_start_m = int(slot[2:4])
        s_end_h = int(slot[5:7])
        slot_start_mins = s_start_h * 60 + s_start_m
        slot_end_mins = s_end_h * 60 if s_end_h != 0 else 24 * 60
        if slot_end_mins <= slot_start_mins:
            slot_end_mins += 24 * 60

        if start_mins_total >= slot_end_mins:
            hourly_target = 0
        elif start_mins_total <= slot_start_mins:
            hourly_target = full_uph
        else:
            active_mins = slot_end_mins - start_mins_total
            hourly_target = int(round((active_mins / 60.0) * full_uph))

        running_cum += hourly_target
        plan_list.append(hourly_target)
        cum_plan_list.append(running_cum)

    return plan_list, cum_plan_list

def calculate_trend_line(actuals_list, logged_mask):
    valid_points = [(i, val) for i, (val, logged) in enumerate(zip(actuals_list, logged_mask)) if logged]
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

class EngineerSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Engineer Setup - Start New Run")
        self.resize(420, 360)
        self.setup_data = None

        layout = QVBoxLayout(self)
        group_run = QGroupBox("Start of Shift / Changeover")
        form_run = QFormLayout()

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setDisplayFormat("dd MMM yyyy")

        self.shift_combo = QComboBox()
        self.shift_combo.addItems(list(SHIFT_HOURS.keys()))

        self.time_line_start = QTimeEdit()
        self.time_line_start.setDisplayFormat("HH:mm")
        self.time_line_start.setTime(QTime(7, 0))

        self.supv_input = QLineEdit()
        self.supv_input.setPlaceholderText("e.g. YENI")
        self.leader_input = QLineEdit()
        self.leader_input.setPlaceholderText("e.g. ROZITA")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g. UPPC4040-0F1B2-Q1A")
        self.line_input = QLineEdit()
        self.line_input.setPlaceholderText("e.g. Q1")
        self.plan_qty_input = QLineEdit()
        self.plan_qty_input.setPlaceholderText("e.g. 378")

        form_run.addRow("Date:", self.date_input)
        form_run.addRow("Shift:", self.shift_combo)
        form_run.addRow("Run Start Time:", self.time_line_start)
        form_run.addRow("Supervisor Name:", self.supv_input)
        form_run.addRow("Leader Name:", self.leader_input)
        form_run.addRow("Model / Part No:", self.model_input)
        form_run.addRow("Line:", self.line_input)
        form_run.addRow("Plan Qty (UPH):", self.plan_qty_input)

        group_run.setLayout(form_run)
        layout.addWidget(group_run)

        btn_box = QHBoxLayout()
        self.start_btn = QPushButton("Start Run")
        self.start_btn.setStyleSheet("padding: 10px; font-weight: bold; background-color: #16a34a; color: white;")
        self.start_btn.clicked.connect(self.on_start)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("padding: 10px;")
        self.cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(self.start_btn)
        btn_box.addWidget(self.cancel_btn)
        layout.addLayout(btn_box)

    def on_start(self):
        try:
            date_str = self.date_input.text().upper()
            shift_key = self.shift_combo.currentText()
            shift_code = "Day" if "Day" in shift_key else "Night"
            start_qtime = self.time_line_start.time()
            start_time_str = start_qtime.toString("HH:mm")

            supv = self.supv_input.text().strip()
            leader = self.leader_input.text().strip()
            model = self.model_input.text().strip()
            line = self.line_input.text().strip()
            uph = int(self.plan_qty_input.text())

            self.setup_data = (date_str, shift_key, shift_code, start_qtime, start_time_str, supv, leader, model, line, uph)
            self.accept()
        except ValueError:
            QMessageBox.critical(self, "Error", "Please fill all fields with valid information (Plan Qty must be a number).")

class PackageRequirementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Package Requirement Status")
        self.resize(500, 350)

        layout = QVBoxLayout(self)
        lbl_title = QLabel("Dashboard System Dependencies & Packages:")
        lbl_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("font-family: monospace; font-size: 13px; background-color: #0f172a; color: #f8fafc; padding: 10px;")
        layout.addWidget(self.text_area)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("padding: 8px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self.check_packages()

    def check_packages(self):
        report = [f"• Python Version: {sys.version.split()[0]} [INSTALLED]\n"]
        try:
            from PyQt6.QtCore import PYQT_VERSION_STR
            report.append(f"• PyQt6 (GUI Framework): v{PYQT_VERSION_STR} [INSTALLED]")
        except ImportError:
            report.append("• PyQt6 (GUI Framework): [NOT INSTALLED] (Required)")
        try:
            report.append(f"• sqlite3 (Local Database): v{sqlite3.version} [INSTALLED]")
        except ImportError:
            report.append("• sqlite3 (Local Database): [NOT INSTALLED] (Required)")
        try:
            import pyqtgraph as pg
            report.append(f"• pyqtgraph (Performance Charts): v{pg.__version__} [INSTALLED]")
        except ImportError:
            report.append("• pyqtgraph (Performance Charts): [NOT INSTALLED] (Optional - Canvas Fallback Active)")

        self.text_area.setText("\n\n".join(report))

class ShiftHistoryDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.selected_shift_id = None
        self.action_type = None

        self.setWindowTitle("Shift History & Run Manager")
        self.resize(550, 420)

        layout = QVBoxLayout(self)
        lbl_title = QLabel("Select a Past Shift Run to Re-Open or Start New:")
        lbl_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("font-size: 13px; padding: 5px;")
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.btn_new = QPushButton("Start New Shift Run")
        self.btn_new.setStyleSheet("padding: 10px; font-weight: bold; background-color: #0284c7; color: white;")
        self.btn_new.clicked.connect(self.on_start_new)

        self.btn_load = QPushButton("Load Selected Run")
        self.btn_load.setStyleSheet("padding: 10px; font-weight: bold; background-color: #16a34a; color: white;")
        self.btn_load.clicked.connect(self.on_load_selected)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("padding: 10px;")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.populate_history()

    def populate_history(self):
        records = self.db.get_all_shift_configs()
        self.list_widget.clear()

        if not records:
            item = QListWidgetItem("No saved shift runs found in database.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            self.btn_load.setEnabled(False)
            return

        for rec in records:
            s_id, date, shift, model, line, uph, leader, supervisor, start_time = rec
            display_text = f"ID #{s_id} | {date} | {shift} | Line {line} | Model: {model} | UPH: {uph} (Start: {start_time})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, s_id)
            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(0)

    def on_load_selected(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            self.selected_shift_id = current_item.data(Qt.ItemDataRole.UserRole)
            if self.selected_shift_id:
                self.action_type = 'load'
                self.accept()

    def on_start_new(self):
        self.action_type = 'new'
        self.accept()

class FallbackChartCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.hours = []
        self.actuals = []
        self.hourly_plans = []
        self.logged_mask = []
        self.show_target = True
        self.show_trend = True
        self.show_labels = True
        self.color_code_bars = True

    def set_chart_options(self, target, trend, labels, color_code):
        self.show_target = target
        self.show_trend = trend
        self.show_labels = labels
        self.color_code_bars = color_code
        self.update()

    def set_data(self, hours, actuals, hourly_plans, logged_mask):
        self.hours = hours
        self.actuals = actuals
        self.hourly_plans = hourly_plans
        self.logged_mask = logged_mask
        self.update()

    def clear_canvas(self):
        self.hours = []
        self.actuals = []
        self.hourly_plans = []
        self.logged_mask = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#0f172a"))
        if not self.hours:
            return

        margin = 60
        chart_w, chart_h = w - (margin * 2), h - (margin * 2)
        max_plan = max(self.hourly_plans) if self.hourly_plans else 1
        max_act = max(self.actuals) if self.actuals else 1
        max_val = max(max_plan, max_act, 1) + 50

        painter.setPen(QPen(QColor("#334155"), 1, Qt.PenStyle.DashLine))
        for i in range(5):
            y = margin + chart_h - (i * (chart_h / 4))
            val = int(i * (max_val / 4))
            painter.drawLine(margin, int(y), margin + chart_w, int(y))
            painter.setPen(QPen(QColor("#94a3b8")))
            painter.drawText(10, int(y) + 5, f"{val}")
            painter.setPen(QPen(QColor("#334155"), 1, Qt.PenStyle.DashLine))

        num_bars = len(self.hours)
        slot_w = chart_w / num_bars
        bar_w = slot_w * 0.35

        for i in range(num_bars):
            is_logged = self.logged_mask[i] if i < len(self.logged_mask) else False
            target = self.hourly_plans[i] if i < len(self.hourly_plans) else 0
            val = self.actuals[i] if i < len(self.actuals) else 0
            slot_x = margin + (i * slot_w)
            
            if is_logged:
                if self.show_target:
                    plan_x = slot_x + (slot_w * 0.1)
                    plan_h = (target / max_val) * chart_h
                    plan_y = margin + chart_h - plan_h
                    painter.setBrush(QBrush(QColor("#f59e0b")))
                    painter.setPen(QPen(QColor("#d97706")))
                    painter.drawRect(int(plan_x), int(plan_y), int(bar_w), int(plan_h))
                    if self.show_labels and target > 0:
                        painter.setPen(QPen(QColor("#fef08a")))
                        painter.drawText(int(plan_x), int(plan_y) - 5, str(target))

                act_x = slot_x + (slot_w * 0.5) if self.show_target else slot_x + (slot_w * 0.25)
                actual_bar_width = bar_w if self.show_target else slot_w * 0.5

                if self.color_code_bars:
                    bar_color, border_color = (QColor("#16a34a"), QColor("#15803d")) if val >= target and target > 0 else (QColor("#dc2626"), QColor("#b91c1c"))
                else:
                    bar_color, border_color = QColor("#3b82f6"), QColor("#1d4ed8")

                act_h = (val / max_val) * chart_h
                act_y = margin + chart_h - act_h
                painter.setBrush(QBrush(bar_color))
                painter.setPen(QPen(border_color))
                painter.drawRect(int(act_x), int(act_y), int(actual_bar_width), int(act_h))

                if self.show_labels and val > 0:
                    painter.setPen(QPen(QColor("#ffffff")))
                    painter.drawText(int(act_x), int(act_y) - 5, str(val))

            painter.setPen(QPen(QColor("#cbd5e1")))
            painter.drawText(int(slot_x + (slot_w * 0.15)), margin + chart_h + 25, self.hours[i][:4])

        if self.show_trend and any(self.logged_mask):
            trend_y = calculate_trend_line(self.actuals, self.logged_mask)
            painter.setPen(QPen(QColor("#38bdf8"), 3, Qt.PenStyle.SolidLine))
            logged_indices = [i for i, l in enumerate(self.logged_mask) if l]
            for idx in range(len(logged_indices) - 1):
                i1, i2 = logged_indices[idx], logged_indices[idx + 1]
                offset_x = (slot_w * 0.675) if self.show_target else (slot_w * 0.5)
                x1 = margin + (i1 * slot_w) + offset_x
                y1 = margin + chart_h - (trend_y[i1] / max_val * chart_h)
                x2 = margin + (i2 * slot_w) + offset_x
                y2 = margin + chart_h - (trend_y[i2] / max_val * chart_h)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

class DashboardWindow(QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.setWindowTitle("Production Dashboard (Monitor 2)")
        self.resize(1920, 1080)
        self.active_hours = SHIFT_HOURS["Day Shift (07:00 - 19:00)"]
        
        self.opt_show_target = True
        self.opt_show_trend = True
        self.opt_show_labels = True
        self.opt_color_code = True
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(15, 15, 15, 15)
        
        self.header_widget = QWidget()
        self.header_layout = QGridLayout(self.header_widget)
        header_font = QFont("Arial", 20, QFont.Weight.Bold)
        
        self.lbl_date = QLabel("DATE: -")
        self.lbl_shift = QLabel("SHIFT: -")
        self.lbl_model = QLabel("MODEL: -")
        self.lbl_supv = QLabel("SUPV: -")
        self.lbl_line = QLabel("LINE: -")
        self.lbl_leader = QLabel("LEADER: -")
        
        self.lbl_clock = QLabel()
        clock_font = QFont("Arial", 22, QFont.Weight.Bold)
        self.lbl_clock.setFont(clock_font)
        self.lbl_clock.setStyleSheet("color: #38bdf8; padding-right: 10px;")
        self.lbl_clock.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        labels = [self.lbl_date, self.lbl_shift, self.lbl_model, 
                  self.lbl_supv, self.lbl_line, self.lbl_leader]
        
        for lbl in labels:
            lbl.setFont(header_font)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.header_layout.addWidget(self.lbl_date, 0, 0)
        self.header_layout.addWidget(self.lbl_shift, 0, 1)
        self.header_layout.addWidget(self.lbl_model, 1, 0)
        self.header_layout.addWidget(self.lbl_supv, 1, 1)
        self.header_layout.addWidget(self.lbl_line, 2, 0)
        
        leader_clock_layout = QHBoxLayout()
        leader_clock_layout.setContentsMargins(0, 0, 0, 0)
        leader_clock_layout.addWidget(self.lbl_leader)
        leader_clock_layout.addWidget(self.lbl_clock)
        self.header_layout.addLayout(leader_clock_layout, 2, 1)
        
        self.layout.addWidget(self.header_widget)
        
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()
        
        self.stack = QStackedWidget()
        self.page_table = QWidget()
        p1_layout = QVBoxLayout(self.page_table)
        p1_layout.setContentsMargins(0, 0, 0, 0)
        
        self.table = QTableWidget(12, 7)
        self.table.setHorizontalHeaderLabels(["TIME", "PLAN (UPH / CUM)", "ACTUAL (HOURLY / CUM)", "DELTA", "YIELD (%)", "DOWNTIME", "REMARKS"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { font-size: 18px; font-weight: bold; gridline-color: #cbd5e1; }
            QHeaderView::section { background-color: #1e293b; color: white; font-size: 18px; font-weight: bold; padding: 10px; border: 1px solid #0f172a; }
            QTableWidget::item { padding: 5px; }
        """)
        p1_layout.addWidget(self.table)
        
        self.page_chart = QWidget()
        p2_layout = QVBoxLayout(self.page_chart)
        p2_layout.setContentsMargins(0, 0, 0, 0)
        
        if HAS_PYQTGRAPH:
            pg.setConfigOption('background', '#0f172a')
            pg.setConfigOption('foreground', '#f8fafc')
            self.chart_widget = pg.PlotWidget(title="Hourly Production Performance: Grouped Plan vs. Actual")
            self.chart_widget.showGrid(x=True, y=True, alpha=0.3)
            p2_layout.addWidget(self.chart_widget)
        else:
            self.chart_widget = FallbackChartCanvas()
            p2_layout.addWidget(self.chart_widget)
            
        self.stack.addWidget(self.page_table)
        self.stack.addWidget(self.page_chart)
        self.layout.addWidget(self.stack)

        self.watermark_label = QLabel("Created by @!&mierol")
        self.watermark_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.watermark_label.setStyleSheet("color: rgba(120, 120, 120, 150); padding-top: 5px;")
        self.watermark_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.layout.addWidget(self.watermark_label)

        self.reset_display()

        self.flip_timer = QTimer(self)
        self.flip_timer.timeout.connect(self.flip_page)

    def update_clock(self):
        current_time = QDateTime.currentDateTime().toString("HH:mm:ss (ddd)")
        self.lbl_clock.setText(f"TIME: {current_time}")

    def set_chart_toggles(self, target, trend, labels, color_code):
        self.opt_show_target = target
        self.opt_show_trend = trend
        self.opt_show_labels = labels
        self.opt_color_code = color_code
        if not HAS_PYQTGRAPH:
            self.chart_widget.set_chart_options(target, trend, labels, color_code)

    def set_auto_flip(self, enabled, interval_seconds):
        if enabled and interval_seconds > 0:
            self.flip_timer.start(interval_seconds * 1000)
        else:
            self.flip_timer.stop()
            self.stack.setCurrentIndex(0)

    def flip_page(self):
        current = self.stack.currentIndex()
        self.stack.setCurrentIndex(1 if current == 0 else 0)

    def reset_display(self):
        self.lbl_date.setText("DATE: -")
        self.lbl_shift.setText("SHIFT: -")
        self.lbl_model.setText("MODEL: -")
        self.lbl_supv.setText("SUPV: -")
        self.lbl_line.setText("LINE: -")
        self.lbl_leader.setText("LEADER: -")
        self.rebuild_table_hours(self.active_hours)
        if HAS_PYQTGRAPH:
            self.chart_widget.clear()
        else:
            self.chart_widget.clear_canvas()

    def rebuild_table_hours(self, hours_list):
        self.active_hours = hours_list
        self.table.clearSpans()
        for i, hour in enumerate(self.active_hours):
            time_item = QTableWidgetItem(hour)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, time_item)
            
            for j in range(1, 7):
                empty_item = QTableWidgetItem("-")
                empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, j, empty_item)
        
    def update_dashboard(self, shift_data, logs, active_hours):
        db_id, date, shift, model, line, cycle_time, uph, leader, supervisor, start_time = shift_data
        
        self.lbl_date.setText(f"DATE: {date}")
        self.lbl_shift.setText(f"SHIFT: {shift}")
        self.lbl_model.setText(f"MODEL: {model}")
        self.lbl_supv.setText(f"SUPV: {supervisor}")
        self.lbl_line.setText(f"LINE: {line}")
        self.lbl_leader.setText(f"LEADER: {leader}")
        
        self.rebuild_table_hours(active_hours)
        hourly_plans, cum_plans = calculate_plan_targets(active_hours, uph, start_time)

        for i in range(12):
            plan_str = f"{hourly_plans[i]} / {cum_plans[i]}"
            plan_item = QTableWidgetItem(plan_str)
            plan_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, plan_item)

        row_logs = {}
        actuals_list = [0] * 12
        logged_mask = [False] * 12

        for idx, log in enumerate(logs):
            hour_block, hourly_actual, cumulative, scrap, downtime, remarks = log
            if hour_block in self.active_hours:
                row = self.active_hours.index(hour_block)
            else:
                row = idx
                
            if row < 12:
                row_logs[row] = (hourly_actual, cumulative, scrap, downtime, remarks)
                actuals_list[row] = hourly_actual
                logged_mask[row] = True
            
            cum_plan_target = cum_plans[row]
            actual_str = f"{hourly_actual} / {cumulative}"
            actual_item = QTableWidgetItem(actual_str)
            actual_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, actual_item)
            
            delta = cumulative - cum_plan_target
            delta_item = QTableWidgetItem(str(delta))
            delta_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if delta < 0:
                delta_item.setForeground(QColor("#dc2626"))
            else:
                delta_item.setForeground(QColor("#16a34a"))
            self.table.setItem(row, 3, delta_item)
            
            yield_perc = ((hourly_actual - scrap) / hourly_actual) * 100 if hourly_actual > 0 else 0.0
            yield_item = QTableWidgetItem(f"{yield_perc:.1f}%")
            yield_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, yield_item)
            
            dt_item = QTableWidgetItem(format_downtime_display(downtime))
            dt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, dt_item)
            
            rmk_item = QTableWidgetItem(str(remarks) if remarks else "-")
            rmk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, rmk_item)

        visited = set()
        for r in range(12):
            if r in visited or r not in row_logs:
                continue
            
            dt_val, rmk_val = row_logs[r][3], row_logs[r][4]
            if not dt_val or not dt_val.strip() or dt_val.strip() == "-":
                continue
                
            span = 1
            while (r + span) in row_logs:
                next_dt, next_rmk = row_logs[r + span][3], row_logs[r + span][4]
                if next_dt and next_dt.strip() and next_dt != "-" and next_rmk == rmk_val:
                    span += 1
                else:
                    break
            
            if span > 1:
                start_time_str = dt_val.split("-")[0].strip()
                last_dt_val = row_logs[r + span - 1][3]
                end_time_str = last_dt_val.split("-")[1].strip()
                merged_range_str = f"{start_time_str}-{end_time_str}"
                formatted_merged_dt = format_downtime_display(merged_range_str)
                
                merged_dt_item = QTableWidgetItem(formatted_merged_dt)
                merged_dt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 5, merged_dt_item)
                
                self.table.setSpan(r, 5, span, 1)
                self.table.setSpan(r, 6, span, 1)
                for s_i in range(r, r + span):
                    visited.add(s_i)

        self.update_chart(active_hours, actuals_list, hourly_plans, logged_mask)

    def update_chart(self, hours, actuals, hourly_plans, logged_mask):
        if HAS_PYQTGRAPH:
            self.chart_widget.clear()
            
            x_logged = [i for i, l in enumerate(logged_mask) if l]
            ticks = [(i, h[:4]) for i, h in enumerate(hours)]
            ax = self.chart_widget.getAxis('bottom')
            ax.setTicks([ticks])
            
            if not x_logged:
                return

            filtered_plans = [hourly_plans[i] for i in x_logged]
            filtered_actuals = [actuals[i] for i in x_logged]
            
            if self.opt_show_target:
                x_plan = [p - 0.18 for p in x_logged]
                bg_plan = pg.BarGraphItem(x=x_plan, height=filtered_plans, width=0.35, brush='#f59e0b', name="Plan Target")
                self.chart_widget.addItem(bg_plan)

            x_act = [p + 0.18 for p in x_logged] if self.opt_show_target else x_logged
            act_width = 0.35 if self.opt_show_target else 0.5
            
            act_brushes = []
            for act, tgt in zip(filtered_actuals, filtered_plans):
                if self.opt_color_code:
                    act_brushes.append(QColor("#16a34a") if act >= tgt and tgt > 0 else QColor("#dc2626"))
                else:
                    act_brushes.append(QColor("#3b82f6"))
                    
            bg_act = pg.BarGraphItem(x=x_act, height=filtered_actuals, width=act_width, brushes=act_brushes, name="Actual Output")
            self.chart_widget.addItem(bg_act)
            
            if self.opt_show_trend and len(x_logged) >= 2:
                trend_full = calculate_trend_line(actuals, logged_mask)
                trend_filtered = [trend_full[i] for i in x_logged]
                self.chart_widget.plot(x_act, trend_filtered, pen=pg.mkPen(color='#38bdf8', width=3), symbol='o', symbolBrush='#38bdf8', name="Performance Trend")
            
            if self.opt_show_labels:
                for idx, i in enumerate(x_logged):
                    if self.opt_show_target and filtered_plans[idx] > 0:
                        txt_p = pg.TextItem(text=str(filtered_plans[idx]), color='#fef08a', anchor=(0.5, 1))
                        txt_p.setPos(x_plan[idx], filtered_plans[idx])
                        self.chart_widget.addItem(txt_p)
                    
                    if filtered_actuals[idx] > 0:
                        txt_a = pg.TextItem(text=str(filtered_actuals[idx]), color='#ffffff', anchor=(0.5, 1))
                        txt_a.setPos(x_act[idx], filtered_actuals[idx])
                        self.chart_widget.addItem(txt_a)
        else:
            self.chart_widget.set_chart_options(self.opt_show_target, self.opt_show_trend, self.opt_show_labels, self.opt_color_code)
            self.chart_widget.set_data(hours, actuals, hourly_plans, logged_mask)

    def closeEvent(self, event):
        QApplication.quit()

class OperatorWindow(QMainWindow):
    data_updated = pyqtSignal(tuple, list, list) 

    def __init__(self, db_manager, dashboard_ref):
        super().__init__()
        self.db = db_manager
        self.dashboard = dashboard_ref
        self.active_shift_id = None
        self.active_shift_data = None
        self.active_hours = SHIFT_HOURS["Day Shift (07:00 - 19:00)"]
        
        self.setWindowTitle("Operator Kiosk")
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(6)
        
        self.setup_menu_bar()
        self.setup_operator_section()

    def setup_menu_bar(self):
        menu_bar = self.menuBar()
        
        file_menu = menu_bar.addMenu("File")
        new_run_action = QAction("New Shift Run (Engineer Setup)", self)
        new_run_action.setShortcut(QKeySequence("Ctrl+N"))
        new_run_action.triggered.connect(self.open_engineer_setup_dialog)
        file_menu.addAction(new_run_action)
        file_menu.addSeparator()

        export_action = QAction("Export Data to CSV", self)
        export_action.triggered.connect(self.export_to_csv)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        
        exit_action = QAction("Exit App", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        history_menu = menu_bar.addMenu("History")
        open_history_action = QAction("Open Shift History / Re-open Run", self)
        open_history_action.triggered.connect(self.open_history_dialog)
        history_menu.addAction(open_history_action)
        
        settings_menu = menu_bar.addMenu("Settings")
        flip_menu = settings_menu.addMenu("Auto-Flip Carousel")
        self.act_flip_off = QAction("Disabled", self, checkable=True)
        self.act_flip_10s = QAction("10 Seconds", self, checkable=True)
        self.act_flip_30s = QAction("30 Seconds", self, checkable=True)
        self.act_flip_60s = QAction("60 Seconds", self, checkable=True)
        self.act_flip_1h  = QAction("1 Hour", self, checkable=True)
        self.act_flip_off.setChecked(True)
        
        flip_group = QActionGroup(self)
        for act in [self.act_flip_off, self.act_flip_10s, self.act_flip_30s, self.act_flip_60s, self.act_flip_1h]:
            flip_group.addAction(act)
            flip_menu.addAction(act)
            
        self.act_flip_off.triggered.connect(lambda: self.on_flip_menu_changed(False, 0))
        self.act_flip_10s.triggered.connect(lambda: self.on_flip_menu_changed(True, 10))
        self.act_flip_30s.triggered.connect(lambda: self.on_flip_menu_changed(True, 30))
        self.act_flip_60s.triggered.connect(lambda: self.on_flip_menu_changed(True, 60))
        self.act_flip_1h.triggered.connect(lambda: self.on_flip_menu_changed(True, 3600))
        
        settings_menu.addSeparator()
        
        self.act_show_plan = QAction("Show Plan Bars (Side-by-Side)", self, checkable=True)
        self.act_show_plan.setChecked(True)
        self.act_show_plan.triggered.connect(self.on_chart_menu_changed)
        settings_menu.addAction(self.act_show_plan)

        self.act_show_trend = QAction("Show Performance Trend Line", self, checkable=True)
        self.act_show_trend.setChecked(True)
        self.act_show_trend.triggered.connect(self.on_chart_menu_changed)
        settings_menu.addAction(self.act_show_trend)

        self.act_show_labels = QAction("Show Bar Value Labels", self, checkable=True)
        self.act_show_labels.setChecked(True)
        self.act_show_labels.triggered.connect(self.on_chart_menu_changed)
        settings_menu.addAction(self.act_show_labels)

        self.act_color_bars = QAction("Color-code Bars (Green/Red)", self, checkable=True)
        self.act_color_bars.setChecked(True)
        self.act_color_bars.triggered.connect(self.on_chart_menu_changed)
        settings_menu.addAction(self.act_color_bars)

        admin_menu = menu_bar.addMenu("Admin")
        check_pkg_action = QAction("Check Requirement Packages", self)
        check_pkg_action.triggered.connect(self.open_package_checker)
        admin_menu.addAction(check_pkg_action)
        admin_menu.addSeparator()
        clear_db_action = QAction("Clear / Empty Database", self)
        clear_db_action.triggered.connect(self.clear_database_prompt)
        admin_menu.addAction(clear_db_action)
        
        view_menu = menu_bar.addMenu("View")
        toggle_tv_action = QAction("Toggle TV Fullscreen", self)
        toggle_tv_action.triggered.connect(self.toggle_tv_fullscreen)
        view_menu.addAction(toggle_tv_action)
        
        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About Software", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def open_engineer_setup_dialog(self):
        dialog = EngineerSetupDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.setup_data:
            date_str, shift_key, shift_code, start_qtime, start_time_str, supv, leader, model, line, uph = dialog.setup_data
            
            self.active_hours = SHIFT_HOURS[shift_key]
            self.hour_combo.clear()
            self.hour_combo.addItems(self.active_hours)
            
            sh_str = start_qtime.toString("HH")
            for idx, slot in enumerate(self.active_hours):
                if slot.startswith(sh_str):
                    self.hour_combo.setCurrentIndex(idx)
                    break

            self.sync_time_pickers()
            cycle_time = 0.0
            
            self.active_shift_id = self.db.save_shift_config(date_str, shift_code, model, line, cycle_time, uph, leader, supv, start_time_str)
            
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT * FROM shift_config WHERE id = ?", (self.active_shift_id,))
            self.active_shift_data = cursor.fetchone()
            
            self.op_group.setEnabled(True)
            QTimer.singleShot(0, self.machine_total_input.setFocus)
            
            QMessageBox.information(self, "Run Started", f"New run started for {shift_key} at {start_time_str}!")
            self.refresh_dashboard()

    def open_package_checker(self):
        dialog = PackageRequirementDialog(self)
        dialog.exec()

    def clear_database_prompt(self):
        reply = QMessageBox.warning(
            self,
            "Confirm Database Wipe",
            "Are you sure you want to CLEAR the entire database?\n\nThis will permanently delete ALL shift configurations and logged actuals!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_database()
            self.active_shift_id = None
            self.active_shift_data = None
            self.dashboard.reset_display()
            QMessageBox.information(self, "Database Cleared", "The database has been wiped successfully.")

    def open_history_dialog(self):
        dialog = ShiftHistoryDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.action_type == 'load' and dialog.selected_shift_id:
                self.load_shift_by_id(dialog.selected_shift_id)
            elif dialog.action_type == 'new':
                self.open_engineer_setup_dialog()

    def load_shift_by_id(self, shift_id):
        config = self.db.get_shift_config_by_id(shift_id)
        if config:
            self.active_shift_data = config
            self.active_shift_id = config[0]
            shift_code = config[2]
            shift_key = "Day Shift (07:00 - 19:00)" if shift_code == "Day" else "Night Shift (19:00 - 07:00)"
            self.active_hours = SHIFT_HOURS[shift_key]
            
            self.hour_combo.clear()
            self.hour_combo.addItems(self.active_hours)
            self.sync_time_pickers()
            
            self.op_group.setEnabled(True)
            self.refresh_dashboard()
            QTimer.singleShot(0, self.machine_total_input.setFocus)

    def on_flip_menu_changed(self, enabled, seconds):
        self.dashboard.set_auto_flip(enabled, seconds)

    def on_chart_menu_changed(self):
        target = self.act_show_plan.isChecked()
        trend = self.act_show_trend.isChecked()
        labels = self.act_show_labels.isChecked()
        color_code = self.act_color_bars.isChecked()
        self.dashboard.set_chart_toggles(target, trend, labels, color_code)
        if self.active_shift_id:
            self.refresh_dashboard()

    def export_to_csv(self):
        try:
            home_dir = os.path.expanduser("~")
            default_path = os.path.join(home_dir, "Desktop", "production_data.csv")
            filename, _ = QFileDialog.getSaveFileName(self, "Export Production Logs", default_path, "CSV Files (*.csv)")
            
            if filename:
                cursor = self.db.conn.cursor()
                cursor.execute('''
                    SELECT s.date, s.shift, s.line, s.model, s.supervisor_name, s.leader_name, s.uph, s.start_time,
                           r.hour_block, r.cumulative_input, r.hourly_actual, r.scrap_input, r.downtime, r.remarks, r.timestamp
                    FROM raw_machine_logs r
                    JOIN shift_config s ON r.shift_id = s.id
                ''')
                rows = cursor.fetchall()
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "Date", "Shift", "Line", "Model", "Supervisor", "Leader", "Plan UPH", "Start Time",
                        "Hour Block", "Cumulative Total", "Hourly Actual", "Scrap", "Downtime", "Remarks", "Logged Time"
                    ])
                    writer.writerows(rows)
                QMessageBox.information(self, "Export Successful", f"Data exported successfully to:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{str(e)}")

    def toggle_tv_fullscreen(self):
        if self.dashboard.isFullScreen():
            self.dashboard.showNormal()
        else:
            self.dashboard.showFullScreen()

    def show_about(self):
        QMessageBox.about(
            self, "About Digital Production Board",
            "<b>Digital Production Board v2.0</b><br><br>"
            "A dual-screen factory monitoring tool designed for Raspberry Pi & Debian OS.<br><br>"
            "<b>Developer:</b> @!&mierol<br>"
            "<b>Database:</b> Local SQLite3<br>"
            "<b>GUI Framework:</b> PyQt6"
        )

    def setup_operator_section(self):
        self.op_group = QGroupBox("Hourly Data Entry")
        self.op_group.setEnabled(True)
        form = QFormLayout()
        form.setContentsMargins(6, 8, 6, 8)
        form.setVerticalSpacing(6)
        
        self.hour_combo = QComboBox()
        self.hour_combo.addItems(self.active_hours)
        self.hour_combo.currentIndexChanged.connect(self.sync_time_pickers)
        
        self.machine_total_input = QLineEdit()
        self.machine_total_input.setPlaceholderText("Enter NXT total")
        
        self.scrap_input = QLineEdit()
        self.scrap_input.setPlaceholderText("0")
        
        self.chk_enable_dt = QCheckBox("Log Downtime")
        self.chk_enable_dt.toggled.connect(self.toggle_dt_pickers)
        
        self.time_dt_start = QTimeEdit()
        self.time_dt_start.setDisplayFormat("HH:mm")
        self.time_dt_start.setEnabled(False)
        
        self.time_dt_end = QTimeEdit()
        self.time_dt_end.setDisplayFormat("HH:mm")
        self.time_dt_end.setEnabled(False)
        
        dt_picker_layout = QHBoxLayout()
        dt_picker_layout.setContentsMargins(0, 0, 0, 0)
        dt_picker_layout.addWidget(self.time_dt_start)
        dt_picker_layout.addWidget(QLabel("to"))
        dt_picker_layout.addWidget(self.time_dt_end)
        
        self.remarks_input = QLineEdit()
        self.remarks_input.setPlaceholderText("e.g., Break Time / Feeder Jam")
        
        self.save_btn = QPushButton("SAVE ACTUALS")
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 15px; font-weight: bold; padding: 10px;")
        self.save_btn.clicked.connect(self.save_actuals)
        
        self.machine_total_input.returnPressed.connect(self.focusNextChild)
        self.scrap_input.returnPressed.connect(self.focusNextChild)
        self.remarks_input.returnPressed.connect(self.save_actuals)
        
        form.addRow("Current Hour:", self.hour_combo)
        form.addRow("Cumulative Total:", self.machine_total_input)
        form.addRow("Scrap / Defects:", self.scrap_input)
        form.addRow("Downtime Event:", self.chk_enable_dt)
        form.addRow("Downtime Range:", dt_picker_layout)
        form.addRow("Remarks:", self.remarks_input)
        
        layout_v = QVBoxLayout()
        layout_v.setContentsMargins(4, 4, 4, 4)
        layout_v.addLayout(form)
        layout_v.addWidget(self.save_btn)
        
        self.op_group.setLayout(layout_v)
        self.main_layout.addWidget(self.op_group)

    def sync_time_pickers(self):
        slot = self.hour_combo.currentText()
        if len(slot) >= 9:
            try:
                sh, sm = int(slot[:2]), int(slot[2:4])
                eh, em = int(slot[5:7]), int(slot[7:9])
                self.time_dt_start.setTime(QTime(sh, sm))
                self.time_dt_end.setTime(QTime(eh, em))
            except ValueError:
                pass

    def toggle_dt_pickers(self, enabled):
        self.time_dt_start.setEnabled(enabled)
        self.time_dt_end.setEnabled(enabled)

    def save_actuals(self):
        if not self.active_shift_id:
            QMessageBox.warning(self, "No Active Run", "Please start a new shift run via File -> New before entering actuals.")
            self.open_engineer_setup_dialog()
            return
            
        try:
            hour_block = self.hour_combo.currentText()
            cumulative = int(self.machine_total_input.text())
            scrap_text = self.scrap_input.text().strip()
            scrap = int(scrap_text) if scrap_text else 0
            user_remarks = self.remarks_input.text().strip()
            uph = self.active_shift_data[6]
            
            if self.chk_enable_dt.isChecked():
                t_start = self.time_dt_start.time()
                t_end = self.time_dt_end.time()
                chunks = split_downtime_picker(t_start, t_end, hour_block, self.active_hours)
            else:
                chunks = [(hour_block, "-")]
            
            primary_slot, primary_dt = chunks[0]
            self.db.log_actuals(self.active_shift_id, primary_slot, cumulative, scrap, uph, primary_dt, user_remarks)
            
            for overflow_slot, overflow_dt in chunks[1:]:
                self.db.log_actuals(self.active_shift_id, overflow_slot, cumulative, 0, uph, overflow_dt, user_remarks)
            
            self.machine_total_input.clear()
            self.scrap_input.clear()
            self.remarks_input.clear()
            self.chk_enable_dt.setChecked(False)
            
            last_filled_slot = chunks[-1][0]
            if last_filled_slot in self.active_hours:
                last_idx = self.active_hours.index(last_filled_slot)
                next_idx = min(last_idx + 1, len(self.active_hours) - 1)
                self.hour_combo.setCurrentIndex(next_idx)
                
            self.refresh_dashboard()
            QTimer.singleShot(0, self.machine_total_input.setFocus)
            
        except ValueError:
            QMessageBox.critical(self, "Error", "Machine Total must be a valid number.")

    def refresh_dashboard(self):
        if self.active_shift_id:
            logs = self.db.get_shift_logs(self.active_shift_id)
            self.data_updated.emit(self.active_shift_data, logs, self.active_hours)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, 'Exit Confirmation',
            'Closing the Operator Kiosk will also shut down the TV Dashboard.\n\nAre you sure you want to exit?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
            QApplication.quit()
        else:
            event.ignore()

if __name__ == "__main__":
    kill_previous_instances()

    app = QApplication(sys.argv)
    db = DatabaseManager()

    dashboard = DashboardWindow(db)
    operator = OperatorWindow(db, dashboard)

    operator.data_updated.connect(dashboard.update_dashboard)

    screens = app.screens()
    op_w, op_h = 380, 480
    
    if len(screens) > 1:
        dashboard.setGeometry(screens[1].geometry())
        dashboard.showFullScreen()
        
        op_geom = screens[0].availableGeometry()
        operator.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        operator.setGeometry(op_geom.x() + op_geom.width() - op_w - 10, 
                             op_geom.y() + op_geom.height() - op_h - 10, 
                             op_w, op_h)
        operator.show()
    else:
        dashboard.show()
        
        op_geom = screens[0].availableGeometry()
        operator.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        operator.setGeometry(op_geom.x() + op_geom.width() - op_w - 10, 
                             op_geom.y() + op_geom.height() - op_h - 40, 
                             op_w, op_h)
        operator.show()

    sys.exit(app.exec())