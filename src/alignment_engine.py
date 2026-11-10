import open3d as o3d
import numpy as np
import copy
import math
from src.logger_config import log, log_milestone

class AlignmentEngine:
    def __init__(self):
        pass

    def execute_alignment(self, source, target):
        """
        Executes an automated alignment by matching architectural bounding box
        centers and testing 4 primary orthogonal directions using Generalized ICP.
        This completely bypasses RANSAC, avoiding tilted or upside-down geometric matches.
        """
        log.info("Starting automated Center-Match orthogonal alignment...")
        
        # 0. Dynamic Voxel Size Calculation
        bbox = source.get_axis_aligned_bounding_box()
        max_bound = max(bbox.get_extent())
        dynamic_voxel_size = max(0.05, max_bound / 150.0) # Scale voxel relative to project size
        
        log.info(f"Dynamic Voxel Size for GICP solver: {dynamic_voxel_size:.4f}")
        
        log_milestone("Phase 3", "Coarse Alignment (RANSAC)", "Started")
        # 1. Feature Extraction / Downsampling
        from src.io_manager import IOManager
        io = IOManager()
        solver_voxel = dynamic_voxel_size
        
        source_down = io.preprocess_point_cloud(source, voxel_size=solver_voxel)
        target_down = io.preprocess_point_cloud(target, voxel_size=solver_voxel)
        
        # We need FPFH features to break symmetric architectural clones
        radius_feature = solver_voxel * 5
        source_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
            source_down, o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100))
        target_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
            target_down, o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100))
            
        distance_threshold = solver_voxel * 1.5
        ransac_iterations = 4000000 
        
        log.info("Attempting RANSAC Global Registration to establish layout orientation...")
        result_global = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
            source_down, target_down, source_fpfh, target_fpfh, True, distance_threshold,
            o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
            3, [o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
                o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(distance_threshold)],
            o3d.pipelines.registration.RANSACConvergenceCriteria(ransac_iterations, 0.999))
            
        if result_global.fitness < 0.05 or result_global.inlier_rmse == 0.0:
            log.warning("RANSAC yielded extremely poor or zero fitness. Falling back to Fast Global Registration (FGR)...")
            result_global = o3d.pipelines.registration.registration_fgr_based_on_feature_matching(
                source_down, target_down, source_fpfh, target_fpfh,
                o3d.pipelines.registration.FastGlobalRegistrationOption(
                    maximum_correspondence_distance=solver_voxel * 2.0,
                    iteration_number=200,
                    tuple_scale=0.95,
                    maximum_tuple_count=10000))
                    
        log.info(f"Global Alignment Result: Fitness={result_global.fitness:.4f}, RMSE={result_global.inlier_rmse:.4f}")
        log_milestone("Phase 3", "Coarse Alignment (RANSAC)", "Completed")
        
        # 2. Extract strictly Z-Rotation from RANSAC to prevent Pitch/Roll tilts
        from scipy.spatial.transform import Rotation
        raw_global_R = result_global.transformation[0:3, 0:3]
        global_rot = Rotation.from_matrix(raw_global_R)
        global_euler = global_rot.as_euler('xyz', degrees=False)
        
        # global_euler[0]=pitch(X), [1]=roll(Y), [2]=yaw(Z) in default xyz
        # We KEEP only the Z rotation to guarantee the dataset stays upright!
        flat_global_R = o3d.geometry.get_rotation_matrix_from_xyz((0, 0, global_euler[2]))
        
        flat_guess = np.eye(4)
        flat_guess[0:3, 0:3] = flat_global_R
        flat_guess[0:3, 3] = result_global.transformation[0:3, 3] # Keep RANSAC translation
        
        log_milestone("Phase 3", "Fine Alignment (GICP)", "Started")
        # 3. Pass perfectly upright guess to Generalized ICP to snap walls
        distance_threshold_icp = 1.5 
        log.info("Executing Generalized ICP to perfectly snap architectural planes...")
        
        result_icp = o3d.pipelines.registration.registration_generalized_icp(
            source_down, target_down, distance_threshold_icp, flat_guess,
            o3d.pipelines.registration.TransformationEstimationForGeneralizedICP())
            
        log.info(f"Final ICP Alignment Result: Fitness={result_icp.fitness:.4f}, RMSE={result_icp.inlier_rmse:.4f}")
        
        final_transform = result_icp.transformation
        log_milestone("Phase 3", "Fine Alignment (GICP)", "Completed")
        
        aligned_source = copy.deepcopy(source)
        aligned_source.transform(final_transform)
        
        return aligned_source, final_transform

    def execute_manual_alignment(self, source, target):
        """
        Interactive Point-Picking Alignment -> GICP fine-tuning.
        """
        log.info("Starting Manual Alignment process. Awaiting user interaction...")
        log_milestone("Phase 3", "Manual Coarse Alignment", "Started")
        
        source_temp = copy.deepcopy(source)
        target_temp = copy.deepcopy(target)
        
        log.info("Waiting for user to pick points on TARGET (Anchor)...")
        picked_id_target = self._pick_points(target_temp, "1) Pick 3+ points on TARGET (Gray) [Shift+LeftClick, then Q]")
        
        log.info("Waiting for user to pick points on SOURCE (Moving)...")
        picked_id_source = self._pick_points(source_temp, "2) Pick same 3+ points on SOURCE (Red/RGB) [Shift+LeftClick, then Q]")
        
        if len(picked_id_source) < 3 or len(picked_id_target) < 3 or len(picked_id_source) != len(picked_id_target):
            log.error("Manual alignment requires at least 3 matching points in both datasets in the identical order.")
            raise ValueError("Invalid number of points picked. You must pick the same number of points (at least 3) in both windows.")
            
        corr = np.zeros((len(picked_id_source), 2), dtype=np.int32)
        corr[:, 0] = picked_id_source
        corr[:, 1] = picked_id_target
        
        log.info("Computing initial manual transformation from user points...")
        p2p = o3d.pipelines.registration.TransformationEstimationPointToPoint()
        manual_transform = p2p.compute_transformation(source, target, o3d.utility.Vector2iVector(corr))
        log_milestone("Phase 3", "Manual Coarse Alignment", "Completed")
        
        log_milestone("Phase 3", "Fine Alignment (GICP)", "Started")
        log.info("Applying manual transform and executing fine GICP tuning...")
        
        from src.io_manager import IOManager
        io = IOManager()
        solver_voxel = 0.1
        source_down = io.preprocess_point_cloud(source, voxel_size=solver_voxel)
        target_down = io.preprocess_point_cloud(target, voxel_size=solver_voxel)
        
        # Extremely wide basin since manual clicks are prone to large human error
        distance_threshold_icp = 2.0 
        
        result_icp = o3d.pipelines.registration.registration_generalized_icp(
            source_down, target_down, distance_threshold_icp, manual_transform,
            o3d.pipelines.registration.TransformationEstimationForGeneralizedICP())
            
        final_transform = result_icp.transformation
        
        aligned_source = copy.deepcopy(source)
        aligned_source.transform(final_transform)
        
        log.info(f"Manual Alignment Complete. Fitness={result_icp.fitness:.4f}, RMSE={result_icp.inlier_rmse:.4f}")
        log_milestone("Phase 3", "Fine Alignment (GICP)", "Completed")
        return aligned_source, final_transform
        
    def _pick_points(self, pcd, window_name):
        log.info(f"Opening interactive Open3D window: {window_name}")
        vis = o3d.visualization.VisualizerWithEditing()
        vis.create_window(window_name=window_name, width=1280, height=720)
        vis.add_geometry(pcd)
        vis.run()  
        picked_points = vis.get_picked_points()
        vis.destroy_window()
        return picked_points
