"""AV Snap desktop studio: Import → Align → Review → Approve → Export."""
import copy
import json
import os
import sys
from pathlib import Path
import numpy as np
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFrame,
    QLabel,QPushButton,QFileDialog,QMessageBox,QTextEdit,QSplitter,QComboBox,QCheckBox,
    QProgressBar,QDoubleSpinBox,QFormLayout,QGridLayout,QScrollArea,QInputDialog,QDialog,QTableWidget,
    QTableWidgetItem,QDialogButtonBox,QShortcut,QSizePolicy)
from src.io_manager import IOManager
from src.project import AlignmentProject
from src.jobs import AlignmentJob,ExportJob
from src.quality import validate_alignment
from src.transforms import from_correspondences
from src.theme import STYLE,icon
from src.viewport import CloudViewport

FORMATS='3D datasets (*.e57 *.las *.laz *.ply *.pcd *.pts *.xyz *.ifc);;All files (*)'


def label(text,role=None):
    widget=QLabel(text); widget.setWordWrap(True)
    if role: widget.setObjectName(role)
    return widget


def card(title):
    frame=QFrame(); frame.setObjectName('glass')
    layout=QVBoxLayout(frame); layout.setContentsMargins(18,18,18,18); layout.setSpacing(12)
    layout.addWidget(label(title,'eyebrow'))
    return frame,layout


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AV Snap — Artificial Vision Alignment Studio')
        self.setWindowIcon(icon()); self.resize(1440,900); self.setMinimumSize(1040,680)
        self.setStyleSheet(STYLE)
        self.project=AlignmentProject(); self.io=IOManager(); self.worker=None; self.export_worker=None
        self.anchor_pcd=None; self.moving_pcd=None; self.aligned_pcd=None; self._busy=False; self._closing=False
        self.dataset_buttons=[]; self.action_buttons=[]
        self.init_ui()
        self.check_run_ready()
        self.log_message('AV Snap ready. Source datasets are preserved; every new transform requires approval.')

    @property
    def anchor_file(self): return self.project.anchor
    @anchor_file.setter
    def anchor_file(self,value): self.project.anchor=value
    @property
    def moving_file(self): return self.project.moving
    @moving_file.setter
    def moving_file(self,value): self.project.moving=value
    @property
    def transform_matrix(self): return self.project.matrix

    def button(self,text,callback,primary=False):
        button=QPushButton(text); button.clicked.connect(callback)
        if primary: button.setObjectName('primary')
        return button

    def init_ui(self):
        root=QWidget(); self.setCentralWidget(root)
        layout=QVBoxLayout(root); layout.setContentsMargins(20,16,20,16); layout.setSpacing(12)
        header,head=card('ARTIFICIAL VISION   /   SPATIAL TOOLS')
        row=QHBoxLayout(); row.addWidget(label('AV Snap','title')); row.addWidget(label('Alignment Studio','muted')); row.addStretch()
        row.addWidget(label('Import  →  Align  →  Review  →  Approve  →  Export','eyebrow')); head.addLayout(row)
        tools=QHBoxLayout()
        self.new_button=self.button('New',self.new_project); self.open_button=self.button('Open project',self.open_project)
        self.save_button=self.button('Save project',self.save_project)
        self.undo_button=self.button('Undo',self.undo); self.redo_button=self.button('Redo',self.redo)
        self.measure_button=self.button('Measure',self.measure)
        for button in [self.new_button,self.open_button,self.save_button,self.undo_button,self.redo_button,self.measure_button]: tools.addWidget(button)
        tools.addStretch(); self.lock_button=self.button('Unlock transform',self.unlock); tools.addWidget(self.lock_button)
        head.addLayout(tools); layout.addWidget(header)
        splitter=QSplitter(Qt.Horizontal)
        left,side=card('01   /   DATASETS')
        side.addWidget(label('Anchor / fixed reference','eyebrow'))
        self.lbl_anchor=label('No anchor selected','muted'); side.addWidget(self.lbl_anchor)
        self.anchor_button=self.button('Import anchor…',self.select_anchor); side.addWidget(self.anchor_button)
        side.addWidget(label('Moving / transformed dataset','eyebrow'))
        self.lbl_moving=label('No moving dataset selected','muted'); side.addWidget(self.lbl_moving)
        self.moving_button=self.button('Import moving…',self.select_moving); side.addWidget(self.moving_button)
        self.dataset_buttons=[self.anchor_button,self.moving_button]
        self.metadata_label=label('Point clouds use project metres. Confirm units before alignment. IFC geometry is converted to SI metres.','muted')
        side.addWidget(self.metadata_label)
        self.units_confirmed=QCheckBox('Point-cloud units are metres'); side.addWidget(self.units_confirmed)
        self.units_confirmed.toggled.connect(self.units_changed)
        side.addStretch()
        side.addWidget(label('Original measurements remain authoritative. Preview sampling never changes export density.','muted'))
        splitter.addWidget(left)
        center,canvas=card('02   /   SPATIAL REVIEW')
        self.viewport=CloudViewport(); canvas.addWidget(self.viewport,1)
        self.metric_label=label('Waiting for datasets','muted'); canvas.addWidget(self.metric_label)
        splitter.addWidget(center)
        right,settings=card('03   /   ALIGNMENT')
        self.preset=QComboBox(); self.preset.addItems(['Fast','Balanced','Quality']); self.preset.setCurrentText('Balanced')
        settings.addWidget(label('Processing quality','muted')); settings.addWidget(self.preset)
        self.upright=QCheckBox('Constrain rotation to upright / yaw'); settings.addWidget(self.upright)
        self.btn_run=self.button('Automatic alignment',self.run_alignment,True)
        self.btn_manual=self.button('Pick correspondences…',self.run_manual_alignment)
        self.control_button=self.button('Enter control points…',self.control_points)
        self.refine_button=self.button('Refine current transform',lambda:self._start('refine'))
        for button in [self.btn_run,self.btn_manual,self.control_button,self.refine_button]: settings.addWidget(button)
        self.candidates=QComboBox(); self.candidates.addItem('Candidate comparison')
        self.candidates.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); self.candidates.setMinimumContentsLength(12)
        self.candidates.activated.connect(self.choose_candidate); settings.addWidget(self.candidates)
        self.edit_toggle=QCheckBox('Translation & rotation adjustments')
        settings.addWidget(self.edit_toggle)
        self.adjust_panel=QWidget(); adjust_layout=QVBoxLayout(self.adjust_panel)
        adjust_layout.setContentsMargins(0,0,0,0)
        adjust_layout.addWidget(label('Metres / degrees · about aligned center','muted'))
        self.edit_toggle.toggled.connect(self.adjust_panel.setVisible)
        form=QGridLayout(); self.adjustments=[]
        for i,name in enumerate(['X','Y','Z','Roll','Pitch','Yaw']):
            spin=QDoubleSpinBox(); spin.setRange(-1e7,1e7) if name in ['X','Y','Z'] else spin.setRange(-180,180)
            spin.setMinimumWidth(0); spin.setMaximumWidth(90); spin.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
            spin.setDecimals(4); spin.setSingleStep(.01 if name in ['X','Y','Z'] else .1)
            form.addWidget(label(name,'muted'),(i//3)*2,i%3); form.addWidget(spin,(i//3)*2+1,i%3); self.adjustments.append(spin)
        adjust_layout.addLayout(form)
        self.adjust_button=self.button('Apply adjustment',self.apply_adjustment); adjust_layout.addWidget(self.adjust_button)
        self.reset_button=self.button('Reset transform',self.reset_transform); adjust_layout.addWidget(self.reset_button)
        self.adjust_panel.hide(); settings.addWidget(self.adjust_panel)
        self.status_label=label('No alignment','eyebrow'); settings.addWidget(self.status_label)
        self.btn_approve=self.button('Approve transform',self.approve); settings.addWidget(self.btn_approve)
        self.btn_export=self.button('Export approved result…',self.export_result,True); settings.addWidget(self.btn_export)
        settings.addStretch()
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(right); scroll.setMinimumWidth(270); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        splitter.addWidget(scroll); splitter.setSizes([270,850,300]); layout.addWidget(splitter,1)
        diagnostics,logs=card('PROCESSING & VALIDATION')
        progress=QHBoxLayout(); self.progress=QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0)
        self.cancel_button=self.button('Cancel job',self.cancel); self.cancel_button.setEnabled(False)
        progress.addWidget(self.progress,1); progress.addWidget(self.cancel_button)
        self.log_toggle=QCheckBox('Show diagnostics'); self.log_toggle.setChecked(False); progress.addWidget(self.log_toggle)
        logs.addLayout(progress)
        self.log_output=QTextEdit(); self.log_output.setReadOnly(True); self.log_output.setMaximumHeight(115)
        self.log_toggle.toggled.connect(self.log_output.setVisible); self.log_output.setVisible(False); logs.addWidget(self.log_output)
        layout.addWidget(diagnostics)
        self.statusBar().showMessage('An Artificial Vision Product.  •  Local processing  •  Rigid transforms in metres')
        for sequence,callback in [('Ctrl+N',self.new_project),('Ctrl+O',self.open_project),('Ctrl+S',self.save_project),('Ctrl+Z',self.undo),('Ctrl+Shift+Z',self.redo)]:
            shortcut=QShortcut(QKeySequence(sequence),self); shortcut.activated.connect(callback)

    def log_message(self,message): self.log_output.append(str(message))

    def _set_busy(self,busy):
        self._busy=busy
        self.progress.setRange(0,0) if busy else self.progress.setRange(0,1)
        self.progress.setValue(0 if busy else 1)
        self.cancel_button.setEnabled(busy and isinstance(self.worker,AlignmentJob) and self.worker.isRunning())
        self.check_run_ready()

    def check_run_ready(self,*args):
        available=bool(self.anchor_file and self.moving_file and self.units_confirmed.isChecked() and not self._busy)
        has_geometry=self.moving_pcd is not None and not self._busy
        locked=self.project.approved
        for button in [self.btn_run,self.btn_manual,self.control_button,self.refine_button]: button.setEnabled(available and not locked)
        for button in self.dataset_buttons+[self.new_button,self.open_button,self.save_button,self.measure_button]: button.setEnabled(not self._busy)
        self.btn_approve.setEnabled(has_geometry and self.units_confirmed.isChecked() and bool(self.project.report) and self.project.report.get('status')!='Failed' and not locked)
        self.btn_export.setEnabled(has_geometry and locked)
        self.lock_button.setEnabled(locked and not self._busy)
        self.edit_toggle.setEnabled(has_geometry and not locked)
        for widget in [self.adjust_button,self.reset_button,self.candidates]+self.adjustments: widget.setEnabled(has_geometry and not locked)
        self.undo_button.setEnabled(has_geometry and bool(self.project.history) and not locked)
        self.redo_button.setEnabled(has_geometry and bool(self.project.future) and not locked)

    def _select(self,kind):
        if self._busy: return
        path,_=QFileDialog.getOpenFileName(self,f'Import {kind} dataset','',FORMATS)
        if not path: return
        anchor,moving=self.anchor_file,self.moving_file
        if kind=='anchor': anchor=path
        else: moving=path
        self.project=AlignmentProject(anchor=anchor,moving=moving)
        self.anchor_pcd=self.moving_pcd=self.aligned_pcd=None
        self.viewport.anchor=self.viewport.moving=None
        if self.viewport.gl:
            for item in self.viewport.items: self.viewport.gl.removeItem(item)
            self.viewport.items=[]
        self.units_confirmed.setChecked(False)
        self.lbl_anchor.setText(Path(anchor).name if anchor else 'No anchor selected')
        self.lbl_moving.setText(Path(moving).name if moving else 'No moving dataset selected')
        self.status_label.setText('Confirm input units, then align')
        self.check_run_ready()
        if anchor and moving: self._start('restore')

    def units_changed(self,checked):
        if not checked:
            self.project.revoke()
        self.check_run_ready()

    def select_anchor(self): self._select('anchor')
    def select_moving(self): self._select('moving')

    def _start(self,operation):
        if self._busy or not self.anchor_file or not self.moving_file: return
        if operation!='restore' and not self.units_confirmed.isChecked():
            QMessageBox.warning(self,'Confirm units','Confirm point-cloud coordinates are in metres first.'); return
        self.project.revoke()
        self.worker=AlignmentJob(self.project,self.io,self.preset.currentText(),self.upright.isChecked(),operation,self)
        self.worker.progress.connect(self.log_message); self.worker.completed.connect(self.handle_finished)
        self.worker.error.connect(self.handle_error); self.worker.finished.connect(self.job_stopped)
        self._set_busy(True); self.worker.start(); self.cancel_button.setEnabled(True)

    def run_alignment(self): self._start('auto')
    def run_manual_alignment(self): self._start('manual')

    def handle_finished(self,result):
        self.anchor_pcd,self.moving_pcd=result['anchor'],result['moving']
        self.project.fingerprints=result['fingerprints']
        self.project.set_transform(result['matrix'],result['report'])
        self.candidates.blockSignals(True); self.candidates.clear(); self.candidates.addItem('Candidate comparison')
        for candidate in result['report'].get('candidates',[]): self.candidates.addItem(f"{candidate['name']} · {candidate['score']:.2f}",candidate)
        self.candidates.blockSignals(False)
        self.metadata_label.setText(f'Anchor: {len(self.anchor_pcd.points):,} points\nMoving: {len(self.moving_pcd.points):,} points\nUnits: metres\nCached reloads: {self.io.cache_hits}')
        self.refresh_review()

    def handle_error(self,message):
        self.project.revoke(); self.log_message(f'ERROR: {message}')
        self.status_label.setText(str(message)); self.check_run_ready()
        if 'cancel' not in str(message).lower() and not self._closing:
            QMessageBox.critical(self,'Processing error',str(message))

    def job_stopped(self):
        self._set_busy(False)
        if self._closing: self.close()

    def cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel(); self.cancel_button.setEnabled(False)
            self.log_message('Cancellation requested. Waiting for the current bounded native operation to finish.')

    def refresh_review(self,revalidate=False):
        if self.moving_pcd is None: return
        if revalidate:
            threshold=max(.02,max(self.moving_pcd.get_axis_aligned_bounding_box().get_extent())/150)*2.5
            report=validate_alignment(self.moving_pcd,self.anchor_pcd,self.project.matrix,threshold).to_dict()
            if report['status']=='Validated':
                report['status']='Needs Review'; report['issues'].append('User-adjusted transform requires review.')
            self.project.report=report
        report=self.project.report
        self.status_label.setText(('APPROVED · ' if self.project.approved else '')+report.get('status','Not validated'))
        self.metric_label.setText(f"Overlap {report.get('source_overlap',0):.1%} / {report.get('target_overlap',0):.1%}   ·   Median {report.get('median_residual_m',0):.4f} m   ·   P95 {report.get('p95_residual_m',0):.4f} m\n"+' '.join(report.get('issues',[])))
        self.viewport.set_clouds(self.anchor_pcd,self.moving_pcd,self.project.matrix)
        self.check_run_ready()

    def approve(self):
        if self._busy or not self.units_confirmed.isChecked(): return
        note=''
        if self.project.report.get('status')!='Validated':
            note,accepted=QInputDialog.getText(self,'Approve reviewed alignment','This result needs review. Record why this transform is acceptable:')
            if not accepted: return
        try:
            self.project.approve(note); self.refresh_review()
        except Exception as error: QMessageBox.warning(self,'Approval blocked',str(error))

    def unlock(self):
        self.project.revoke(); self.refresh_review()

    def choose_candidate(self,index):
        if self._busy or self.project.approved: return
        candidate=self.candidates.itemData(index)
        if candidate:
            self.project.set_transform(candidate['matrix'],{}); self.refresh_review(True)

    def apply_adjustment(self):
        if self._busy or self.project.approved or self.moving_pcd is None: return
        from scipy.spatial.transform import Rotation
        values=[spin.value() for spin in self.adjustments]
        delta=np.eye(4); delta[:3,:3]=Rotation.from_euler('xyz',values[3:],degrees=True).as_matrix()
        center=self.project.matrix[:3,:3]@self.moving_pcd.get_center()+self.project.matrix[:3,3]
        delta[:3,3]=np.array(values[:3])+center-delta[:3,:3]@center
        self.project.set_transform(delta@self.project.matrix,{})
        for spin in self.adjustments: spin.setValue(0)
        self.refresh_review(True)

    def reset_transform(self):
        if self._busy or self.project.approved: return
        self.project.set_transform(np.eye(4),{}); self.refresh_review(True)

    def undo(self):
        if not self._busy and not self.project.approved and self.project.undo(): self.refresh_review(True)
    def redo(self):
        if not self._busy and not self.project.approved and self.project.redo(): self.refresh_review(True)

    def new_project(self):
        if self._busy: return
        self.project=AlignmentProject(); self.anchor_pcd=self.moving_pcd=None; self.io.clear_cache()
        self.viewport.anchor=self.viewport.moving=None
        if self.viewport.gl:
            for item in self.viewport.items: self.viewport.gl.removeItem(item)
            self.viewport.items=[]
        self.lbl_anchor.setText('No anchor selected'); self.lbl_moving.setText('No moving dataset selected')
        self.status_label.setText('No alignment'); self.metric_label.setText('Waiting for datasets')
        self.units_confirmed.setChecked(False); self.check_run_ready()

    def save_project(self):
        if self._busy: return
        path,_=QFileDialog.getSaveFileName(self,'Save alignment project','','AV Snap project (*.avsnap)')
        if path:
            try: self.project.save(path); self.log_message(f'Project saved: {path}')
            except Exception as error: self.handle_error(str(error))

    def open_project(self):
        if self._busy: return
        path,_=QFileDialog.getOpenFileName(self,'Open alignment project','','AV Snap project (*.avsnap)')
        if path:
            try:
                project=AlignmentProject.load(path); self.new_project(); self.project=project
                self.lbl_anchor.setText(Path(project.anchor).name); self.lbl_moving.setText(Path(project.moving).name)
                self.units_confirmed.setChecked(True); self._start('restore')
            except Exception as error: self.handle_error(str(error))

    def export_result(self):
        if self._busy: return
        try: self.project.require_export()
        except Exception as error: QMessageBox.warning(self,'Export blocked',str(error)); return
        ext=Path(self.moving_file).suffix.lower()
        default=str(Path(self.moving_file).with_name(Path(self.moving_file).stem+'_aligned'+(ext if ext in {'.ifc','.e57','.las','.laz'} else '.ply')))
        formats={'ifc':'IFC (*.ifc)','e57':'E57 (*.e57)','las':'LAS (*.las)','laz':'LAZ (*.laz)'}
        native=formats.get(ext[1:],'PLY (*.ply)')
        path,_=QFileDialog.getSaveFileName(self,'Export approved result',default,native+';;PLY (*.ply);;PCD (*.pcd);;XYZ (*.xyz)')
        if not path: return
        self.export_worker=ExportJob(self.project,self.io,self.moving_pcd,path,self)
        self.export_worker.completed.connect(lambda output:self.log_message(f'Export validated: {output} · alignment report saved alongside.'))
        self.export_worker.error.connect(self.handle_error); self.export_worker.finished.connect(self.job_stopped)
        self._set_busy(True); self.export_worker.start()

    def _coordinate_table(self,title,rows,headers):
        dialog=QDialog(self); dialog.setWindowTitle(title); dialog.resize(760,360)
        layout=QVBoxLayout(dialog); table=QTableWidget(rows,len(headers)); table.setHorizontalHeaderLabels(headers)
        for r in range(rows):
            for c in range(len(headers)): table.setItem(r,c,QTableWidgetItem('0'))
        layout.addWidget(table)
        if rows>=3:
            add=self.button('Add correspondence',lambda: table.insertRow(table.rowCount())); layout.addWidget(add)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec_()!=QDialog.Accepted: return None
        return np.array([[float(table.item(r,c).text()) if table.item(r,c) else 0 for c in range(len(headers))] for r in range(table.rowCount())])

    def control_points(self):
        if self._busy or self.project.approved or self.moving_pcd is None: return
        try:
            values=self._coordinate_table('Correspondences in metres · moving → anchor',3,['Moving X','Moving Y','Moving Z','Anchor X','Anchor Y','Anchor Z'])
            if values is None: return
            matrix=from_correspondences(values[:,:3],values[:,3:])
            self.project.set_transform(matrix,{})
            self.refresh_review(True)
            self._start('refine')
            self.log_message('Control-point rigid transform applied; refining from these correspondences.')
        except Exception as error: QMessageBox.warning(self,'Invalid control points',str(error))

    def measure(self):
        if self._busy: return
        try:
            values=self._coordinate_table('Measure two project coordinates in metres',2,['X','Y','Z'])
            if values is not None: QMessageBox.information(self,'Measurement',f'Distance: {np.linalg.norm(values[1]-values[0]):.4f} m')
        except Exception as error: QMessageBox.warning(self,'Invalid coordinates',str(error))

    def closeEvent(self,event):
        active=(self.worker and self.worker.isRunning()) or (self.export_worker and self.export_worker.isRunning())
        if active:
            self._closing=True; self.cancel(); self.log_message('Finishing active work before closing…'); event.ignore()
        else: event.accept()


def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('AV Snap'); app.setOrganizationName('Artificial Vision')
    window=MainWindow(); window.show()
    return app.exec_()

if __name__=='__main__': sys.exit(main())
