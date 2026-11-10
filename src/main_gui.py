import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTextEdit, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from src.io_manager import IOManager
from src.alignment_engine import AlignmentEngine
from src.logger_config import log, log_milestone
import open3d as o3d
import json
import copy

class WorkerThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object, object, object)
    error = pyqtSignal(str)

    def __init__(self, anchor_file, moving_file, is_manual=False):
        super().__init__()
        self.anchor_file = anchor_file
        self.moving_file = moving_file
        self.is_manual = is_manual
        self.io_manager = IOManager()
        self.alignment_engine = AlignmentEngine()

    def run(self):
        try:
            self.progress.emit("Loading Anchor Dataset...")
            anchor_pcd = self.io_manager.load_dataset(self.anchor_file, is_reference=True)
            self.progress.emit("Anchor Dataset Loaded.")

            self.progress.emit("Loading Moving Dataset...")
            moving_pcd = self.io_manager.load_dataset(self.moving_file, is_reference=False)
            self.progress.emit("Moving Dataset Loaded.")

            if self.is_manual:
                self.progress.emit("Aligning datasets MANUALLY (Awaiting user interaction in Open3D...)")
                aligned_pcd, transform_matrix = self.alignment_engine.execute_manual_alignment(moving_pcd, anchor_pcd)
            else:
                self.progress.emit("Aligning datasets AUTOMATICALLY...")
                aligned_pcd, transform_matrix = self.alignment_engine.execute_alignment(moving_pcd, anchor_pcd)
            
            self.progress.emit("Alignment Complete.")
            self.finished.emit(anchor_pcd, moving_pcd, aligned_pcd)
            
            # Save the result so we can export it later
            self.result_aligned_pcd = aligned_pcd
            self.result_transform_matrix = transform_matrix
            
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Dataset Alignment Tool")
        self.resize(800, 600)
        
        self.anchor_file = None
        self.moving_file = None
        
        self.anchor_pcd = None
        self.moving_pcd = None
        self.aligned_pcd = None
        self.transform_matrix = None

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout(main_widget)
        
        # File Selection Area
        file_layout = QVBoxLayout()
        
        # Anchor
        anchor_layout = QHBoxLayout()
        self.lbl_anchor = QLabel("Anchor Request (Reference): None")
        btn_anchor = QPushButton("Select Anchor (Point Cloud / Model)")
        btn_anchor.clicked.connect(self.select_anchor)
        anchor_layout.addWidget(self.lbl_anchor)
        anchor_layout.addWidget(btn_anchor)
        
        # Moving
        moving_layout = QHBoxLayout()
        self.lbl_moving = QLabel("Moving Dataset: None")
        btn_moving = QPushButton("Select Moving Dataset")
        btn_moving.clicked.connect(self.select_moving)
        moving_layout.addWidget(self.lbl_moving)
        moving_layout.addWidget(btn_moving)
        
        file_layout.addLayout(anchor_layout)
        file_layout.addLayout(moving_layout)
        layout.addLayout(file_layout)
        
        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_run = QPushButton("Auto Align")
        self.btn_run.clicked.connect(self.run_alignment)
        self.btn_run.setEnabled(False)
        
        self.btn_manual = QPushButton("Manual Align")
        self.btn_manual.clicked.connect(self.run_manual_alignment)
        self.btn_manual.setEnabled(False)
        
        self.btn_preview = QPushButton("Preview Result")
        self.btn_preview.clicked.connect(self.preview_result)
        self.btn_preview.setEnabled(False)
        
        self.btn_export = QPushButton("Export Result")
        self.btn_export.clicked.connect(self.export_result)
        self.btn_export.setEnabled(False)
        
        action_layout.addWidget(self.btn_run)
        action_layout.addWidget(self.btn_manual)
        action_layout.addWidget(self.btn_preview)
        action_layout.addWidget(self.btn_export)
        
        layout.addLayout(action_layout)
        
        # Log Output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(QLabel("Progress Log:"))
        layout.addWidget(self.log_output)
        
        # We also want to capture the python logging to the GUI
        self.log_message("Tool initialized.")

    def log_message(self, message):
        self.log_output.append(message)
        log.info(message)
        
    def select_anchor(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Anchor File", "", "3D Files (*.e57 *.las *.ply *.pcd *.rcs *.rvt *.ifc)")
        if file:
            self.anchor_file = file
            self.lbl_anchor.setText(f"Anchor: {os.path.basename(file)}")
            self.check_run_ready()
            self.log_message(f"Selected Anchor: {file}")

    def select_moving(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Moving File", "", "3D Files (*.e57 *.las *.ply *.pcd *.rcs *.rvt *.ifc)")
        if file:
            self.moving_file = file
            self.lbl_moving.setText(f"Moving: {os.path.basename(file)}")
            self.check_run_ready()
            self.log_message(f"Selected Moving: {file}")

    def check_run_ready(self):
        if self.anchor_file and self.moving_file:
            self.btn_run.setEnabled(True)
            self.btn_manual.setEnabled(True)

    def run_alignment(self):
        self.log_message("Starting Auto Alignment Worker...")
        self.btn_run.setEnabled(False)
        self.btn_manual.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_preview.setEnabled(False)
        
        self.worker = WorkerThread(self.anchor_file, self.moving_file, is_manual=False)
        self.worker.progress.connect(self.log_message)
        self.worker.error.connect(self.handle_error)
        self.worker.finished.connect(self.handle_finished)
        self.worker.start()

    def run_manual_alignment(self):
        self.log_message("Starting Manual Alignment Worker...")
        self.btn_run.setEnabled(False)
        self.btn_manual.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_preview.setEnabled(False)
        
        self.worker = WorkerThread(self.anchor_file, self.moving_file, is_manual=True)
        self.worker.progress.connect(self.log_message)
        self.worker.error.connect(self.handle_error)
        self.worker.finished.connect(self.handle_finished)
        self.worker.start()

    def handle_error(self, err_msg):
        self.log_message(f"ERROR: {err_msg}")
        QMessageBox.critical(self, "Alignment Error", str(err_msg))
        self.btn_run.setEnabled(True)
        self.btn_manual.setEnabled(True)

    def handle_finished(self, anchor_pcd, moving_pcd, aligned_pcd):
        self.anchor_pcd = anchor_pcd
        self.moving_pcd = moving_pcd
        self.aligned_pcd = aligned_pcd
        self.transform_matrix = self.worker.result_transform_matrix
        
        self.log_message("Alignment Worker finished successfully.")
        self.btn_run.setEnabled(True)
        self.btn_manual.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.btn_export.setEnabled(True)

    def preview_result(self):
        if not self.aligned_pcd or not self.anchor_pcd:
            return
            
        self.log_message("Opening Open3D visualizer for preview...")
        geometries = []
        
        # 1. Anchor (Reference) Dataset
        if self.anchor_file in self.worker.io_manager.loaded_meshes:
            self.log_message("Using original polished 3D mesh for Anchor dataset visualization.")
            anchor_vis = self.worker.io_manager.loaded_meshes[self.anchor_file]
        else:
            anchor_vis = type(self.anchor_pcd)()
            anchor_vis.points = self.anchor_pcd.points
            if self.anchor_pcd.has_colors():
                anchor_vis.colors = self.anchor_pcd.colors
            else:
                anchor_vis.paint_uniform_color([0.5, 0.5, 0.5]) # Gray Fallback
                
        geometries.append(anchor_vis)
        
        # 2. Moving (Aligned) Dataset
        # Deepcopy to preserve full internal orientation matrices rather than just raw point arrays
        aligned_vis = copy.deepcopy(self.aligned_pcd)
        
        if not self.aligned_pcd.has_colors():
            aligned_vis.paint_uniform_color([0, 1, 0]) # Green Fallback
            
        geometries.append(aligned_vis)

        # Force Open3D camera to look at the center with a strict Z-up architectural vector
        o3d.visualization.draw_geometries(geometries, window_name="Alignment Final Preview", 
                                          lookat=[0, 0, 0], up=[0, 0, 1], front=[-1, -1, 1], zoom=0.5)
        
    def export_result(self):
        log_milestone("Phase 5", "Exporting dataset", "Started")
        # Prompt user for export location (default <original>_aligned.ifc)
        default_name = os.path.splitext(os.path.basename(self.moving_file))[0] + "_aligned.ifc"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Aligned IFC",
            os.path.join(os.path.dirname(self.moving_file), default_name),
            "IFC Files (*.ifc)"
        )
        if not save_path:
            self.log_message("Export cancelled by user.")
            log_milestone("Phase 5", "Exporting dataset", "Cancelled")
            return
        try:
            # Export using IOManager which now handles native IFC export and validation
            self.worker.io_manager.export_dataset(
                self.aligned_pcd,
                save_path,
                original_file_path=self.moving_file,
                transform_matrix=self.transform_matrix,
            )
            self.log_message(f"Export Complete. Saved to {save_path}")
            log_milestone("Phase 5", "Exporting dataset", "Completed")
            QMessageBox.information(self, "Export Complete", f"Saved to {save_path}")
        except Exception as e:
            self.log_message(f"Export failed: {e}")
            log_milestone("Phase 5", "Exporting dataset", "Failed")
            QMessageBox.critical(self, "Export Error", str(e))


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
