import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('AV_SNAP_HEADLESS','1')
import tempfile
import unittest
from pathlib import Path
import numpy as np
import open3d as o3d
from PyQt5.QtWidgets import QApplication
from src.main_gui import MainWindow
from src.jobs import AlignmentJob,ExportJob
from src.project import fingerprint
from src.theme import BrandSplash

app=QApplication.instance() or QApplication([])


class GuiTests(unittest.TestCase):
    def test_initial_state_splash_scaling_and_window_controls(self):
        w=MainWindow(); w.show(); app.processEvents()
        self.assertFalse(w.btn_export.isEnabled()); self.assertFalse(w.btn_run.isEnabled())
        self.assertFalse(w.btn_approve.isEnabled())
        w.showMaximized(); app.processEvents(); self.assertTrue(w.isMaximized())
        w.showNormal(); w.resize(1040,680); app.processEvents()
        splash=BrandSplash(); splash.status('Preparing alignment studio'); splash.show(); app.processEvents(); splash.close()
        self.assertFalse(splash.pixmap().isNull()); w.close()

    def test_review_approval_and_edit_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=str(Path(d)/'a.ply'),str(Path(d)/'b.ply')
            pc=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.random.default_rng(2).uniform(size=(200,3))))
            o3d.io.write_point_cloud(a,pc); o3d.io.write_point_cloud(b,pc)
            w=MainWindow(); w.project.anchor=a; w.project.moving=b
            report={'status':'Validated','source_overlap':1.,'target_overlap':1.,'median_residual_m':0.,'p95_residual_m':0.}
            w.handle_finished({'anchor':pc,'moving':pc,'matrix':np.eye(4),'report':report,'fingerprints':{'anchor':fingerprint(a),'moving':fingerprint(b)}})
            w.units_confirmed.setChecked(True)
            self.assertTrue(w.btn_approve.isEnabled()); self.assertFalse(w.btn_export.isEnabled())
            w.approve(); self.assertTrue(w.btn_export.isEnabled()); self.assertFalse(w.adjust_button.isEnabled())
            w.unlock(); w.adjustments[0].setValue(.1); w.apply_adjustment()
            self.assertFalse(w.project.approved); self.assertFalse(w.btn_export.isEnabled())
            w.undo(); self.assertAlmostEqual(w.project.matrix[0,3],0.)
            w.new_project(); self.assertIsNone(w.moving_pcd); self.assertFalse(w.btn_export.isEnabled()); w.close()

    def test_worker_result_is_complete_and_export_runs_only_after_approval(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=str(Path(d)/'a.ply'),str(Path(d)/'b.ply')
            pc=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.random.default_rng(5).uniform(size=(600,3))))
            o3d.io.write_point_cloud(a,pc); o3d.io.write_point_cloud(b,pc)
            w=MainWindow(); w.project.anchor=a; w.project.moving=b
            worker=AlignmentJob(w.project,w.io,preset='Fast')
            results=[]; errors=[]; worker.completed.connect(results.append); worker.error.connect(errors.append)
            worker.run(); app.processEvents()
            self.assertFalse(errors); self.assertEqual(len(results),1)
            self.assertIn('matrix',results[0]); self.assertIn('report',results[0])
            w.handle_finished(results[0]); w.project.approve('Synthetic known-identical geometry reviewed')
            output=str(Path(d)/'out.ply'); job=ExportJob(w.project,w.io,pc,output)
            job.error.connect(errors.append); job.run(); app.processEvents()
            self.assertFalse(errors); self.assertTrue(Path(output).exists()); self.assertTrue(Path(output+'.alignment.json').exists())
            w.close()

    def test_background_job_keeps_event_loop_alive_and_cancel_can_recover(self):
        from PyQt5.QtCore import QEventLoop,QTimer
        with tempfile.TemporaryDirectory() as d:
            a,b=str(Path(d)/'a.ply'),str(Path(d)/'b.ply')
            pc=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.random.default_rng(7).uniform(size=(1000,3))))
            o3d.io.write_point_cloud(a,pc); o3d.io.write_point_cloud(b,pc)
            w=MainWindow(); w.project.anchor=a; w.project.moving=b
            cancelled=AlignmentJob(w.project,w.io); cancelled.cancel()
            errors=[]; cancelled.error.connect(errors.append); cancelled.run(); app.processEvents()
            self.assertTrue(errors and 'cancel' in errors[0].lower())
            self.assertFalse(w.io.cancelled())
            worker=AlignmentJob(w.project,w.io,preset='Fast')
            loop=QEventLoop(); timer=QTimer(); timer.setInterval(5); heartbeats=[]
            timer.timeout.connect(lambda:heartbeats.append(1))
            results=[]; worker.completed.connect(results.append); worker.finished.connect(loop.quit)
            timeout=QTimer(); timeout.setSingleShot(True); timeout.timeout.connect(loop.quit); timeout.start(15000)
            timer.start(); worker.start(); loop.exec_(); timer.stop(); timeout.stop()
            if worker.isRunning(): worker.cancel(); worker.wait(15000)
            self.assertFalse(worker.isRunning()); self.assertTrue(results); self.assertGreater(len(heartbeats),0)
            output=str(Path(d)/'unapproved.ply')
            job=ExportJob(w.project,w.io,pc,output); failures=[]; job.error.connect(failures.append); job.run(); app.processEvents()
            self.assertTrue(failures); self.assertFalse(Path(output).exists()); w.close()
