import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, pyqtSignal
from src.io_manager import IOManager
import traceback

class WorkerThread(QThread):
    finished = pyqtSignal()
    
    def run(self):
        print("WorkerThread running...")
        try:
            io = IOManager()
            # the _load_e57 handles the subprocess now
            pcd = io._load_e57('C:/Users/callen/Downloads/2026-02-24_Mens.e57')
            print("Successfully loaded e57 points via QThread!")
            print(f"Points loaded: {len(pcd.points)}")
        except Exception as e:
            print(f"Error in WorkerThread: {e}")
            traceback.print_exc()
        finally:
            self.finished.emit()

app = QApplication(sys.argv)
worker = WorkerThread()
worker.finished.connect(app.quit)
worker.start()
sys.exit(app.exec_())
