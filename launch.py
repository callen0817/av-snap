"""Offline launcher: dependency installation belongs to setup, never startup."""
import os
import sys


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--e57-worker':
        from src.e57_worker import main as run
        run(sys.argv[2:]); return 0
    if len(sys.argv)>1 and sys.argv[1]=='--desktop-worker':
        from src.desktop_worker import main as run
        run(sys.argv[2:]); return 0
    try:
        from PyQt5.QtCore import Qt,QTimer
        from PyQt5.QtWidgets import QApplication,QMessageBox
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,True)
        app=QApplication(sys.argv)
        app.setApplicationName('AV Snap'); app.setOrganizationName('Artificial Vision')
        from src.theme import BrandSplash
        splash=BrandSplash(); splash.show(); splash.status('Loading geometry engine…'); app.processEvents()
        from src.main_gui import MainWindow
        splash.status('Preparing alignment studio…'); app.processEvents()
        window=MainWindow(); window.show(); splash.finish(window)
        if '--smoke-test' in sys.argv:
            def verify():
                try:
                    assert window.windowTitle().startswith('AV Snap')
                    assert not window.btn_export.isEnabled()
                    assert not window.btn_approve.isEnabled()
                    window.grab().save(os.environ.get('AV_SNAP_SCREENSHOT','/tmp/av-snap-smoke.png'))
                    print('PASS packaged/startup GUI smoke',flush=True)
                    app.exit(0)
                except Exception:
                    import traceback
                    traceback.print_exc(); app.exit(1)
            QTimer.singleShot(300,verify)
        return app.exec_()
    except Exception as error:
        import traceback
        traceback.print_exc()
        message=f'AV Snap could not start: {error}\nInstall requirements.txt in your virtual environment, then retry. No packages are installed during launch.'
        try:
            from PyQt5.QtWidgets import QApplication,QMessageBox
            app=QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None,'AV Snap startup error',message)
        except Exception:
            print(message,file=sys.stderr)
        return 1

if __name__=='__main__':
    sys.exit(main())
