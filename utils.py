import os
import signal
import subprocess
from datetime import datetime, timedelta

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


def format_duration_str(mins: int) -> str:
    if mins >= 60:
        hrs = mins // 60
        m = mins % 60
        return f"{hrs}h {m}m" if m > 0 else f"{hrs}h"
    return f"{mins}m"


def format_downtime_display(downtime_str: str) -> str:
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


def split_downtime_picker(start_qtime, end_qtime, start_slot: str, active_hours: list) -> list:
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


def calculate_plan_targets(active_hours: list, full_uph: int, start_time_str: str):
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


def calculate_trend_line(actuals_list: list, logged_mask: list) -> list:
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


def kill_previous_instances():
    """Kill previously running instances of the dashboard main.py process."""
    current_pid = os.getpid()
    try:
        output = subprocess.check_output(["pgrep", "-f", "main.py"]).decode().split()
        for pid_str in output:
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid != current_pid:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
    except subprocess.CalledProcessError:
        # pgrep exits with non-zero when no process found
        pass
