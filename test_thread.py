import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread
import pye57

class WorkerThread(QThread):
    def run(self):
        print("T: Start", flush=True)
        e57 = pye57.E57('C:/Users/callen/Downloads/2026-02-24_Mens.e57')
        print("T: Read", flush=True)
        data = e57.read_scan_raw(0, ignore_unsupported_fields=True)
        print("T: Done", flush=True)

app = QApplication(sys.argv)
worker = WorkerThread()
worker.start()
worker.finished.connect(app.quit)
sys.exit(app.exec_())
