import pye57
import threading

def run():
    print("T: Start", flush=True)
    e57 = pye57.E57('C:/Users/callen/Downloads/2026-02-24_Mens.e57')
    print("T: Read", flush=True)
    data = e57.read_scan_raw(0, ignore_unsupported_fields=True)
    print("T: Done", flush=True)

t = threading.Thread(target=run)
t.start()
t.join()
print("Main Done")
