import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.io_manager import IOManager
from src.alignment_engine import AlignmentEngine
import open3d as o3d
import numpy as np

def run():
    io = IOManager()
    engine = AlignmentEngine()
    
    print("Loading datasets...")
    target = io.load_dataset("C:/Users/callen/Downloads/Bergdorf Goodman MTM Corner.ifc")
    source = io.load_dataset("C:/Users/callen/Downloads/2026-02-24_Mens.e57")
    
    # We can use the preprocessor from AlignmentEngine directly via io if we want
    print("Executing alignment...")
    aligned_source, matrix = engine.execute_alignment(source, target)
    
    print("Evaluating final alignment fitness...")
    # Evaluate fitness
    eval_result = o3d.pipelines.registration.evaluate_registration(
        aligned_source, target, 0.2, np.eye(4))
    print(eval_result)
    
    print("Opening Local Visualizer...")
    # Paint them so we can tell them apart
    target.paint_uniform_color([0.8, 0.8, 0.8]) # Gray BIM
    aligned_source.paint_uniform_color([1.0, 0.0, 0.0]) # Red Scan
    o3d.visualization.draw_geometries([target, aligned_source], zoom=0.5, front=[-1, -1, 1], lookat=[0, 0, 0], up=[0, 0, 1])
    
if __name__ == "__main__":
    run()
