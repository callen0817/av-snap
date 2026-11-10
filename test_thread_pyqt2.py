import sys
import threading
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal
import pye57

class Worker(QObject):
    finished = pyqtSignal()
    
    def __init__(self, e57_obj):
        super().__init__()
        self.e57 = e57_obj
        
    def run(self):
        print("T: Read", flush=True)
        data = self.e57.read_scan_raw(0, ignore_unsupported_fields=True)
        print("T: Done", flush=True)
        self.finished.emit()

app = QApplication(sys.argv)
print("Main: creating e57", flush=True)
e57 = pye57.E57('C:/Users/callen/Downloads/2026-02-24_Mens.e57')
print("Main: created", flush=True)

worker = Worker(e57)
t = threading.Thread(target=worker.run)
worker.finished.connect(app.quit)
t.start()
sys.exit(app.exec_())
