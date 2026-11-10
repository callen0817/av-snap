import open3d as o3d
import numpy as np
import copy
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.io_manager import IOManager

def run():
    io = IOManager()
    print("Loading datasets...")
    target = io.load_dataset("C:/Users/callen/Downloads/Bergdorf Goodman MTM Corner.ifc")
    source = io.load_dataset("C:/Users/callen/Downloads/2026-02-24_Mens.e57")
    
    print("Preprocessing...")
    target_down = io.preprocess_point_cloud(target, voxel_size=0.1)
    source_down = io.preprocess_point_cloud(source, voxel_size=0.1)
    
    source_center = source_down.get_center()
    target_center = target_down.get_center()
    translation_vector = target_center - source_center
    
    print(f"Translation Vector: {translation_vector}")
    
    best_fitness = -1
    best_icp = None
    best_yaw = 0
    
    # We test 4 orientations after translating source to target center
    for yaw in [0, 90, 180, 270]:
        rad = np.radians(yaw)
        rot_mat = o3d.geometry.get_rotation_matrix_from_xyz((0, 0, rad))
        
        # 1. Shift source to origin
        T_neg = np.eye(4)
        T_neg[0:3, 3] = -source_center
        
        # 2. Rotate
        R = np.eye(4)
        R[0:3, 0:3] = rot_mat
        
        # 3. Shift to target center
        T_pos = np.eye(4)
        T_pos[0:3, 3] = target_center
        
        # Combined
        initial_guess = np.dot(T_pos, np.dot(R, T_neg))
        
        # Coarse ICP with large threshold (1.5 meters)
        icp_coarse = o3d.pipelines.registration.registration_generalized_icp(
            source_down, target_down, 1.5, initial_guess,
            o3d.pipelines.registration.TransformationEstimationForGeneralizedICP())
            
        print(f"Yaw {yaw} -> Coarse Fitness: {icp_coarse.fitness:.4f}, RMSE: {icp_coarse.inlier_rmse:.4f}")
        
        if icp_coarse.fitness > best_fitness:
            best_fitness = icp_coarse.fitness
            best_icp = icp_coarse
            best_yaw = yaw
            
    print(f"Best Yaw: {best_yaw}, Fitness: {best_icp.fitness}")
    
    # Visualize best (Forced Z-Up Camera)
    source.transform(best_icp.transformation)
    target.paint_uniform_color([0.8, 0.8, 0.8])
    source.paint_uniform_color([1.0, 0.0, 0.0])
    o3d.visualization.draw_geometries([target, source], zoom=0.5, front=[-1, -1, 1], lookat=[0, 0, 0], up=[0, 0, 1])

if __name__ == "__main__":
    run()
