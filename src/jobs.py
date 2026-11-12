"""Background Qt jobs; result data is complete before delivery to the GUI."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import numpy as np
import open3d as o3d
from PyQt5.QtCore import QThread, pyqtSignal
from src.alignment_engine import AlignmentEngine
from src.quality import validate_alignment
from src.project import fingerprint,atomic_json


class AlignmentJob(QThread):
    progress=pyqtSignal(str)
    completed=pyqtSignal(object)
    error=pyqtSignal(str)

    def __init__(self,project,io,preset='Balanced',upright=False,operation='auto',parent=None):
        super().__init__(parent)
        self.project=copy.deepcopy(project); self.io=io
        self.preset=preset; self.upright=upright; self.operation=operation
        self.stop=threading.Event()

    def cancel(self): self.stop.set()

    def checkpoint(self):
        if self.stop.is_set(): raise InterruptedError('Operation cancelled.')

    def run(self):
        try:
            self.io.cancelled=self.stop.is_set
            self.progress.emit('Loading anchor dataset…'); self.checkpoint()
            fingerprints={'anchor':fingerprint(self.project.anchor),'moving':fingerprint(self.project.moving)}
            anchor=self.io.load_dataset(self.project.anchor); self.checkpoint()
            self.progress.emit('Loading moving dataset…')
            moving=self.io.load_dataset(self.project.moving); self.checkpoint()
            engine=AlignmentEngine(self.preset,self.upright,self.stop.is_set,self.progress.emit)
            if self.operation=='restore':
                matrix=self.project.matrix
                threshold=max(.02,max(moving.get_axis_aligned_bounding_box().get_extent())/150)*2.5
                report=validate_alignment(moving,anchor,matrix,threshold).to_dict()
                # Candidate ambiguity from previous sessions is not assumed resolved.
                if report['status']=='Validated':
                    report['status']='Needs Review'; report['issues'].append('Restored transform requires renewed review; competing candidates were not rerun.')
            elif self.operation=='refine':
                _,matrix=engine.refine_initial(moving,anchor,self.project.matrix)
                report=engine.last_report.to_dict()
            elif self.operation=='manual':
                self.progress.emit('Pick corresponding points in the Open3D windows, then press Q.')
                with tempfile.TemporaryDirectory(prefix='av-snap-manual-') as d:
                    source,target,output,report_path=[str(Path(d)/name) for name in ['source.ply','target.ply','matrix.npy','report.json']]
                    o3d.io.write_point_cloud(source,moving); o3d.io.write_point_cloud(target,anchor)
                    command=[sys.executable,'--desktop-worker'] if getattr(sys,'frozen',False) else [sys.executable,'-m','src.desktop_worker']
                    process=subprocess.Popen(command+[source,target,output,report_path],cwd=Path(__file__).resolve().parent.parent)
                    try:
                        while True:
                            self.checkpoint()
                            try: code=process.wait(timeout=.2); break
                            except subprocess.TimeoutExpired: pass
                        if code: raise RuntimeError('Manual point picking failed. Check the desktop display and selected correspondences.')
                        matrix=np.load(output,allow_pickle=False)
                        report=json.loads(Path(report_path).read_text())
                    finally:
                        if process.poll() is None: process.terminate(); process.wait(timeout=10)
            else:
                _,matrix=engine.execute_alignment(moving,anchor)
                report=engine.last_report.to_dict()
            self.checkpoint()
            if fingerprints!={'anchor':fingerprint(self.project.anchor),'moving':fingerprint(self.project.moving)}:
                raise ValueError('Source files changed during processing. Reload and retry.')
            self.completed.emit({'anchor':anchor,'moving':moving,'matrix':matrix,'report':report,'fingerprints':fingerprints})
        except Exception as error:
            self.error.emit(str(error))
        finally:
            self.io.cancelled=lambda: False


class ExportJob(QThread):
    completed=pyqtSignal(str)
    error=pyqtSignal(str)

    def __init__(self,project,io,cloud,destination,parent=None):
        super().__init__(parent)
        self.project=copy.deepcopy(project); self.io=io; self.cloud=cloud; self.destination=destination

    def run(self):
        try:
            self.project.require_export()
            # Never relabel a reprojected cloud with the source CRS. Reprojection
            # is a separate explicit operation, outside rigid registration.
            if Path(self.project.moving).suffix.lower() in {'.las','.laz'} and Path(self.project.anchor).suffix.lower() in {'.las','.laz'}:
                import laspy
                with laspy.open(self.project.moving) as a, laspy.open(self.project.anchor) as b:
                    source_crs,anchor_crs=a.header.parse_crs(),b.header.parse_crs()
                    if source_crs is not None and anchor_crs is not None and source_crs!=anchor_crs:
                        raise ValueError('LAS coordinate reference systems differ. Reproject a copy into the anchor CRS before native export.')
            aligned=copy.deepcopy(self.cloud).transform(self.project.matrix)
            validation=self.io.export_dataset(aligned,self.destination,self.project.moving,self.project.matrix)
            self.project.verify_sources()
            report=self.project.to_dict(); report['export_validation']=validation; report['export_file']=str(Path(self.destination).resolve())
            atomic_json(self.destination+'.alignment.json',report)
            self.completed.emit(self.destination)
        except Exception as error:
            self.error.emit(str(error))
