import tempfile
import unittest
from pathlib import Path
import numpy as np
import open3d as o3d
import pye57
import laspy
from src.io_manager import IOManager


class IOTests(unittest.TestCase):
    def test_multiscan_e57_pose_color_intensity_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = str(Path(d)/'source.e57'), str(Path(d)/'out.e57')
            data = {'cartesianX':np.array([0.,1.,2.]), 'cartesianY':np.array([0.,0.,1.]),'cartesianZ':np.array([1.,2.,3.]),'intensity':np.array([.1,.2,.8]),'colorRed':np.array([10,20,30],dtype=np.uint8),'colorGreen':np.array([40,50,60],dtype=np.uint8),'colorBlue':np.array([70,80,90],dtype=np.uint8)}
            with pye57.E57(source,mode='w') as writer:
                writer.write_scan_raw(data,translation=np.array([10.,0.,0.]),rotation=np.array([1.,0.,0.,0.]))
                writer.write_scan_raw(data,translation=np.array([0.,20.,0.]),rotation=np.array([2**-.5,0.,0.,2**-.5]))
            io = IOManager(); pc = io.load_dataset(source)
            self.assertEqual(len(pc.points),6)
            np.testing.assert_allclose(np.asarray(pc.points)[:3],np.column_stack([data['cartesianX']+10,data['cartesianY'],data['cartesianZ']]))
            np.testing.assert_allclose(np.asarray(pc.points)[3:],np.column_stack([-data['cartesianY'],data['cartesianX']+20,data['cartesianZ']]),atol=1e-8)
            np.testing.assert_allclose(io.attributes[source]['intensity'],np.tile(data['intensity'],2))
            t = np.eye(4); t[:3,3]=[2,3,4]
            io.export_dataset(pc,output,source,t)
            actual = IOManager().load_dataset(output)
            np.testing.assert_allclose(actual.points,np.asarray(pc.points)+[2,3,4],atol=1e-6)
            np.testing.assert_allclose(actual.colors,pc.colors)

    def test_las_preserves_attributes_and_coordinates(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = str(Path(d)/'source.las'), str(Path(d)/'out.las')
            data=laspy.LasData(laspy.LasHeader(point_format=3,version='1.2'))
            data.x=[1,2,3]; data.y=[4,5,6]; data.z=[7,8,9]
            data.classification=[1,2,6]; data.intensity=[12,34,56]
            data.write(source)
            io=IOManager(); pc=io.load_dataset(source)
            t=np.eye(4); t[:3,3]=[10,20,30]
            io.export_dataset(pc,output,source,t)
            actual=laspy.read(output)
            np.testing.assert_allclose(actual.x,[11,12,13])
            np.testing.assert_array_equal(actual.classification,data.classification)
            np.testing.assert_array_equal(actual.intensity,data.intensity)

    def test_cache_invalidates_changes_and_does_not_expose_mutable_data(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'points.ply'); io=IOManager()
            pc=o3d.geometry.PointCloud(o3d.utility.Vector3dVector([[0.,0.,0.],[1.,2.,3.]]))
            o3d.io.write_point_cloud(path,pc)
            first=io.load_dataset(path); first.translate([1,1,1])
            second=io.load_dataset(path)
            np.testing.assert_allclose(second.points,pc.points)
            self.assertEqual(io.cache_hits,1)
            pc.translate([10,0,0]); o3d.io.write_point_cloud(path,pc)
            np.testing.assert_allclose(io.load_dataset(path).points,pc.points)

    def test_unsupported_and_invalid_exports_do_not_create_files(self):
        io=IOManager()
        for ext in ['rvt','rcs','rcp']:
            with self.assertRaisesRegex(ValueError,'Convert'):
                io.load_dataset('missing.'+ext)
        with tempfile.TemporaryDirectory() as d:
            output=str(Path(d)/'bad.ifc')
            with self.assertRaises(ValueError):
                io.export_dataset(o3d.geometry.PointCloud(),output)
            self.assertFalse(Path(output).exists())
