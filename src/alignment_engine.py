"""Bounded candidate registration with multi-resolution GICP and independent QA."""
import copy
import time
import numpy as np
import open3d as o3d
from src.io_manager import IOManager
from src.quality import validate_alignment
from src.transforms import rigid_matrix, from_correspondences


class AlignmentEngine:
    PRESETS = {'Fast': (15_000, 20), 'Balanced': (40_000, 40), 'Quality': (80_000, 60)}

    def __init__(self, preset='Balanced', upright=False, cancelled=None, progress=None):
        self.preset = preset
        self.upright = upright
        self.cancelled = cancelled or (lambda: False)
        self.progress = progress or (lambda message: None)
        self.last_report = None
        self._prepared_cache = {}

    def _checkpoint(self, message):
        if self.cancelled():
            raise InterruptedError('Alignment cancelled; no transform approved.')
        self.progress(message)

    def _prepare(self, cloud, voxel):
        key = (id(cloud), float(voxel))
        if key in self._prepared_cache:
            return self._prepared_cache[key][1]
        points = np.asarray(cloud.points)
        if len(points) < 30 or not np.isfinite(points).all():
            raise ValueError('Alignment needs at least 30 finite points per dataset.')
        if max(cloud.get_axis_aligned_bounding_box().get_extent()) <= 1e-8:
            raise ValueError('Dataset has no spatial extent.')
        prepared = IOManager().preprocess_point_cloud(cloud, voxel, noise_filter=True)
        self._prepared_cache[key] = (cloud, prepared)
        return prepared

    def _refine(self, source, target, initial, voxel):
        matrix = rigid_matrix(initial)
        iterations = self.PRESETS[self.preset][1]
        for level in [4,2,1]:
            self._checkpoint(f'Refining at {voxel*level:.3f} m resolution')
            a, b = self._prepare(source,voxel*level), self._prepare(target,voxel*level)
            result = o3d.pipelines.registration.registration_generalized_icp(
                a,b,voxel*level*2.5,matrix,
                o3d.pipelines.registration.TransformationEstimationForGeneralizedICP(kernel=o3d.pipelines.registration.TukeyLoss(k=voxel*level*2.5)),
                o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=iterations))
            matrix = rigid_matrix(result.transformation)
            if self.upright:
                yaw = np.arctan2(matrix[1,0],matrix[0,0])
                matrix[:3,:3] = o3d.geometry.get_rotation_matrix_from_xyz([0,0,yaw])
        return matrix

    def execute_alignment(self, source, target):
        self._prepared_cache.clear()
        start = time.perf_counter()
        self._checkpoint('Validating coordinates and preparing coarse geometry')
        if self.preset not in self.PRESETS:
            raise ValueError('Unknown processing preset.')
        extent = max(source.get_axis_aligned_bounding_box().get_extent())
        voxel = max(.02,extent/150)
        # Bound solver point counts by increasing voxel size; retain original clouds.
        a,b = self._prepare(source,voxel),self._prepare(target,voxel)
        while max(len(a.points),len(b.points)) > self.PRESETS[self.preset][0]:
            voxel *= 1.5
            a,b = self._prepare(source,voxel),self._prepare(target,voxel)
        candidates = [('Existing coordinates',np.eye(4))]
        for yaw in [0,np.pi/2,np.pi,3*np.pi/2]:
            matrix = np.eye(4)
            matrix[:3,:3] = o3d.geometry.get_rotation_matrix_from_xyz([0,0,yaw])
            matrix[:3,3] = b.get_center()-matrix[:3,:3]@a.get_center()
            candidates.append((f'Architectural yaw {np.degrees(yaw):.0f}°',matrix))
        self._checkpoint('Matching geometric features (bounded global search)')
        coarse_a,coarse_b = self._prepare(a,voxel*2),self._prepare(b,voxel*2)
        param = o3d.geometry.KDTreeSearchParamHybrid(radius=voxel*10,max_nn=100)
        fa = o3d.pipelines.registration.compute_fpfh_feature(coarse_a,param)
        fb = o3d.pipelines.registration.compute_fpfh_feature(coarse_b,param)
        try:
            global_result = o3d.pipelines.registration.registration_fgr_based_on_feature_matching(
                coarse_a,coarse_b,fa,fb,o3d.pipelines.registration.FastGlobalRegistrationOption(maximum_correspondence_distance=voxel*4,iteration_number=48))
            if global_result.fitness < .15:
                global_result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
                    coarse_a,coarse_b,fa,fb,True,voxel*4,
                    o3d.pipelines.registration.TransformationEstimationPointToPoint(False),3,
                    [o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(.9),o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(voxel*4)],
                    o3d.pipelines.registration.RANSACConvergenceCriteria(30_000,.99))
            candidates.append(('Feature matching',global_result.transformation))
        except RuntimeError as error:
            self.progress(f'Feature matching unavailable: {error}; evaluating coordinate/yaw candidates.')
        evaluated = []
        for label,guess in candidates:
            self._checkpoint(f'Evaluating {label}')
            matrix = self._refine(a,b,guess,voxel)
            report = validate_alignment(a,b,matrix,voxel*2.5)
            evaluated.append((report.score, -report.p95_residual_m,label,matrix,report))
        evaluated.sort(key=lambda item: (item[0],item[1]),reverse=True)
        _,_,_,matrix,report = evaluated[0]
        # Compare distinct, similarly plausible solutions; equivalent initializations
        # that converge to the same transform do not count as ambiguity.
        for score,_,label,alternative,_ in evaluated[1:]:
            angle = np.arccos(np.clip((np.trace(matrix[:3,:3].T@alternative[:3,:3])-1)/2,-1,1))
            shift = np.linalg.norm(matrix[:3,3]-alternative[:3,3])
            if score >= report.score-.03 and (angle > np.radians(5) or shift > voxel*3):
                if report.status != 'Failed': report.status = 'Needs Review'
                report.issues.append(f'Competing solution: {label}. Repetitive geometry may be ambiguous.')
                break
        report.candidates = [{'name':e[2],'score':e[0],'p95_residual_m':-e[1],'matrix':e[3].tolist()} for e in evaluated]
        report.elapsed_seconds = time.perf_counter()-start
        try:
            import psutil
            report.rss_mb_at_completion = psutil.Process().memory_info().rss/1024**2
        except ImportError:
            pass
        self.last_report = report
        self._checkpoint('Registration complete; review before approving export')
        aligned = copy.deepcopy(source).transform(matrix)
        return aligned,matrix

    def refine_initial(self, source, target, initial):
        self._prepared_cache.clear()
        voxel = max(.02,max(source.get_axis_aligned_bounding_box().get_extent())/150)
        matrix = self._refine(source,target,initial,voxel)
        self.last_report = validate_alignment(source,target,matrix,voxel*2.5)
        if self.last_report.status == 'Validated':
            self.last_report.status = 'Needs Review'
            self.last_report.issues.append('User initialization refined; independent alternative candidates were not compared.')
        return copy.deepcopy(source).transform(matrix),matrix

    def refine_correspondences(self, source, target, source_points, target_points):
        matrix = from_correspondences(source_points,target_points)
        return self.refine_initial(source,target,matrix)

    def execute_manual_alignment(self, source, target):
        # The GUI launches this in an isolated process; Open3D owns that process's
        # main thread instead of creating a second GUI toolkit in a Qt worker.
        ids_target = self._pick_points(target,'Pick 3+ TARGET points in order, then Q')
        ids_source = self._pick_points(source,'Pick matching MOVING points in order, then Q')
        return self.refine_correspondences(source,target,np.asarray(source.points)[ids_source],np.asarray(target.points)[ids_target])

    def _pick_points(self, cloud, title):
        visualizer = o3d.visualization.VisualizerWithEditing()
        if not visualizer.create_window(window_name=title,width=1000,height=700):
            raise RuntimeError('Interactive point picking requires a working desktop/OpenGL display.')
        try:
            visualizer.add_geometry(cloud); visualizer.run()
            return visualizer.get_picked_points()
        finally:
            visualizer.destroy_window()
