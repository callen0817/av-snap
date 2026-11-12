import unittest
import numpy as np
import open3d as o3d
from src.alignment_engine import AlignmentEngine
from src.quality import validate_alignment
from src.transforms import rigid_matrix, from_correspondences


def cloud(points):
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))


class AlignmentTests(unittest.TestCase):
    def test_known_rigid_registration(self):
        points=np.random.default_rng(12).uniform([0,0,0],[3,2,1],(2000,3))
        target=cloud(points)
        rotation=o3d.geometry.get_rotation_matrix_from_xyz([0,0,.13])
        source=cloud(points@rotation.T+[.3,-.2,.1])
        engine=AlignmentEngine('Fast')
        aligned,matrix=engine.execute_alignment(source,target)
        self.assertLess(np.mean(aligned.compute_point_cloud_distance(target)),.015)
        np.testing.assert_allclose(matrix[:3,:3],rotation.T,atol=.01)
        np.testing.assert_allclose(matrix[:3,3],-rotation.T@np.array([.3,-.2,.1]),atol=.01)
        self.assertNotEqual(engine.last_report.status,'Failed')

    def test_independent_validation_rejects_no_overlap_and_flags_plane(self):
        points=np.random.default_rng(2).uniform(size=(1000,3))
        report=validate_alignment(cloud(points),cloud(points+100),np.eye(4),.01)
        self.assertEqual(report.status,'Failed')
        points[:,2]=0
        report=validate_alignment(cloud(points),cloud(points),np.eye(4),.01)
        self.assertEqual(report.status,'Needs Review')

    def test_control_points_and_degeneracy(self):
        a=np.array([[0,0,0],[1,0,0],[0,1,0]])
        t=from_correspondences(a,a+[1,2,3])
        np.testing.assert_allclose(t[:3,3],[1,2,3])
        for invalid in [np.zeros((3,3)),np.array([[0,0,0],[1,0,0],[2,0,0]])]:
            with self.assertRaises(ValueError): from_correspondences(invalid,invalid)
        t[0,0]=2
        with self.assertRaises(ValueError): rigid_matrix(t)

    def test_cancel_and_insufficient_input(self):
        engine=AlignmentEngine(cancelled=lambda:True)
        with self.assertRaises(InterruptedError): engine.execute_alignment(cloud(np.ones((30,3))),cloud(np.ones((30,3))))
        with self.assertRaises(ValueError): AlignmentEngine().execute_alignment(cloud(np.ones((2,3))),cloud(np.ones((2,3))))

    def test_symmetric_competing_solutions_are_never_validated(self):
        grid=np.stack(np.meshgrid(np.linspace(0,1,10),np.linspace(0,1,10),np.linspace(0,1,10)),axis=-1).reshape(-1,3)
        engine=AlignmentEngine('Fast')
        engine.execute_alignment(cloud(grid),cloud(grid))
        self.assertEqual(engine.last_report.status,'Needs Review')
        self.assertTrue(any('Competing' in issue for issue in engine.last_report.issues))
