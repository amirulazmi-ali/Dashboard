import sys
from PyQt6.QtWidgets import QApplication, QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QPushButton

class ShiftHistoryDialog(QDialog):
    def __init__(self, records):
        super().__init__()
        self.setWindowTitle("Shift History v1.8")
        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        for r in records:
            self.list_widget.addItem(QListWidgetItem(f"ID #{r[0]} | {r[1]} | Shift: {r[2]} | Line: {r[3]}"))
        layout.addWidget(self.list_widget)

        btn = QPushButton("Load Shift Run")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dummy_data = [(1, "2026-08-24", "Day", "L1"), (2, "2026-08-24", "Night", "L2")]
    dlg = ShiftHistoryDialog(dummy_data)
    dlg.exec()
    sys.exit(0)