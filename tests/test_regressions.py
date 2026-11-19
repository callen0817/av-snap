import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('AV_SNAP_HEADLESS', '1')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import open3d as o3d
import pye57
import laspy
from PyQt5.QtWidgets import QApplication

from src.alignment_engine import AlignmentEngine
from src.e57_worker import _normalize_e57_colors, transform_file
from src.io_manager import IOManager
from src.jobs import ExportJob
from src.main_gui import MainWindow, _append_filter_extension, _truncate_status
from src.project import AlignmentProject, fingerprint
from src.viewport import CloudViewport

app = QApplication.instance() or QApplication([])


def _cloud(points):
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))


class RegressionTests(unittest.TestCase):
    def test_upright_true_preserves_translation_on_non_origin_utm_cloud(self):
        rng = np.random.default_rng(42)
        offset = np.array([100.0, 200.0, 50.0])
        local = rng.uniform([0, 0, 0], [4, 3, 2], (1500, 3))
        target_pts = local + offset
        yaw = 0.08
        r_yaw = o3d.geometry.get_rotation_matrix_from_xyz([0, 0, yaw])
        c = target_pts.mean(axis=0)
        source_pts = (target_pts - c) @ r_yaw.T + c + np.array([0.1, -0.1, 0.05])
        source = _cloud(source_pts)
        target = _cloud(target_pts)

        engine = AlignmentEngine(preset='Fast', upright=True)
        aligned, matrix = engine.refine_initial(source, target, np.eye(4))
        mean_dist = float(np.mean(aligned.compute_point_cloud_distance(target)))
        self.assertLess(mean_dist, 0.02)
        # Rotation must remain pure yaw (no roll/pitch)
        np.testing.assert_allclose(matrix[2, :3], [0.0, 0.0, 1.0], atol=1e-6)
        np.testing.assert_allclose(matrix[:3, 2], [0.0, 0.0, 1.0], atol=1e-6)

        # Also directly verify centroid compensation at UTM scale when GICP returns roll/pitch
        utm_pts = local + np.array([500_000.0, 4_500_000.0, 100.0])
        utm_cloud = _cloud(utm_pts)
        utm_c = np.asarray(utm_cloud.get_center())
        tilted = np.eye(4)
        tilted[:3, :3] = o3d.geometry.get_rotation_matrix_from_xyz([0.02, -0.015, 0.25])
        tilted[:3, 3] = utm_c - tilted[:3, :3] @ utm_c + np.array([1.0, -2.0, 0.5])
        fake_res = MagicMock()
        fake_res.transformation = tilted
        with patch('open3d.pipelines.registration.registration_generalized_icp', return_value=fake_res):
            out_matrix = engine._refine(utm_cloud, utm_cloud, np.eye(4), 0.1)
        # Centroid image must be preserved (within 1e-6 m, not shifted by ~100 km)
        expected_c = tilted[:3, :3] @ utm_c + tilted[:3, 3]
        actual_c = out_matrix[:3, :3] @ utm_c + out_matrix[:3, 3]
        np.testing.assert_allclose(actual_c, expected_c, atol=1e-6)
        np.testing.assert_allclose(out_matrix[2, :3], [0.0, 0.0, 1.0], atol=1e-6)

    def test_refine_initial_enforces_preset_point_budget(self):
        rng = np.random.default_rng(9)
        pts = rng.uniform([0, 0, 0], [5, 5, 2], (3000, 3))
        source, target = _cloud(pts), _cloud(pts + np.array([0.05, 0.0, 0.0]))
        engine = AlignmentEngine(preset='Fast')
        seen_counts = []
        original_refine = engine._refine

        def spy_refine(a, b, initial, voxel):
            seen_counts.append(max(len(a.points), len(b.points)))
            return original_refine(a, b, initial, voxel)

        with patch.dict(AlignmentEngine.PRESETS, {'Fast': (500, 10)}), \
             patch.object(engine, '_refine', side_effect=spy_refine):
            engine.refine_initial(source, target, np.eye(4))
        self.assertEqual(len(seen_counts), 1)
        self.assertLessEqual(seen_counts[0], 500)

    def test_e57_nan_attributes_and_16bit_float_color_normalization(self):
        # Unit tests for 16-bit, 8-bit, and float [0, 1] color normalization
        valid = np.array([True, True, True])
        c16 = _normalize_e57_colors({
            'colorRed': np.array([0, 32768, 65535], dtype=np.uint16),
            'colorGreen': np.array([65535, 0, 32768], dtype=np.uint16),
            'colorBlue': np.array([32768, 65535, 0], dtype=np.uint16),
        }, valid)
        np.testing.assert_allclose(c16[0], [0.0, 1.0, 32768 / 65535.0], atol=1e-6)
        np.testing.assert_allclose(c16[2], [1.0, 32768 / 65535.0, 0.0], atol=1e-6)

        cfloat = _normalize_e57_colors({
            'colorRed': np.array([0.0, 0.5, 1.0], dtype=np.float32),
            'colorGreen': np.array([0.2, 0.4, 0.8], dtype=np.float32),
            'colorBlue': np.array([1.0, 0.5, 0.0], dtype=np.float32),
        }, valid)
        np.testing.assert_allclose(cfloat[:, 0], [0.0, 0.5, 1.0], atol=1e-6)

        # Roundtrip E57 with 16-bit colors and invalid points
        with tempfile.TemporaryDirectory() as d:
            source, output = str(Path(d) / 'nan16.e57'), str(Path(d) / 'out.e57')
            data = {
                'cartesianX': np.array([0.0, 1.0, 2.0]),
                'cartesianY': np.array([0.0, 1.0, 0.0]),
                'cartesianZ': np.array([1.0, 2.0, 3.0]),
                'cartesianInvalidState': np.array([0, 1, 0], dtype=np.int8),
                'colorRed': np.array([0, 32768, 65535], dtype=np.uint16),
                'colorGreen': np.array([65535, 32768, 0], dtype=np.uint16),
                'colorBlue': np.array([0, 65535, 32768], dtype=np.uint16),
            }
            with pye57.E57(source, mode='w') as writer:
                writer.write_scan_raw(data, translation=np.zeros(3), rotation=np.array([1.0, 0.0, 0.0, 0.0]))
            io = IOManager()
            pc = io.load_dataset(source)
            colors = np.asarray(pc.colors)
            self.assertEqual(len(pc.points), 2)
            self.assertLessEqual(float(colors.max()), 1.0)
            self.assertGreaterEqual(float(colors.min()), 0.0)
            np.testing.assert_allclose(colors[0], [0.0, 1.0, 0.0], atol=1e-4)
            np.testing.assert_allclose(colors[1, 0], 1.0, atol=1e-4)

            # Verify transform_file tolerates NaN coordinates and attributes (equal_nan=True)
            t = np.eye(4)
            t[:3, 3] = [1.0, 2.0, 3.0]
            orig_read_scan = pye57.E57.read_scan

            def read_scan_with_nans(self_e57, *args, **kwargs):
                res = orig_read_scan(self_e57, *args, **kwargs)
                res = dict(res)
                res['cartesianX'] = np.append(res['cartesianX'], np.nan)
                res['cartesianY'] = np.append(res['cartesianY'], np.nan)
                res['cartesianZ'] = np.append(res['cartesianZ'], np.nan)
                res['intensity'] = np.array([0.5, np.nan, 0.8])
                return res

            with patch.object(pye57.E57, 'read_scan', read_scan_with_nans):
                transform_file(source, output, t)
            self.assertTrue(Path(output).exists())

    def test_las_export_updates_header_mins_and_maxs(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = str(Path(d) / 'source.las'), str(Path(d) / 'out.las')
            data = laspy.LasData(laspy.LasHeader(point_format=3, version='1.2'))
            data.x = [1.0, 2.0, 3.0]
            data.y = [4.0, 5.0, 6.0]
            data.z = [7.0, 8.0, 9.0]
            data.write(source)
            io = IOManager()
            pc = io.load_dataset(source)
            t = np.eye(4)
            t[:3, 3] = [100.0, -50.0, 25.0]
            io.export_dataset(pc, output, source, t)
            actual = laspy.read(output)
            np.testing.assert_allclose(actual.header.mins, [101.0, -46.0, 32.0], atol=1e-3)
            np.testing.assert_allclose(actual.header.maxs, [103.0, -44.0, 34.0], atol=1e-3)

    def test_verify_sources_revokes_on_missing_or_empty_path_and_load_validates_schema(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.ply', Path(d) / 'b.ply'
            a.write_text('anchor')
            b.write_text('moving')
            p = AlignmentProject(
                anchor=str(a),
                moving=str(b),
                report={'status': 'Validated'},
                fingerprints={'anchor': fingerprint(a), 'moving': fingerprint(b)},
            )
            p.approve()
            self.assertTrue(p.approved)
            # Delete moving file -> must revoke and raise ValueError (not FileNotFoundError)
            b.unlink()
            with self.assertRaises(ValueError):
                p.verify_sources()
            self.assertFalse(p.approved)

            # Empty path must also revoke and raise ValueError
            p.approved = True
            p.moving = ''
            with self.assertRaises(ValueError):
                p.verify_sources()
            self.assertFalse(p.approved)

            # Invalid project JSON types rejected in load()
            bad = Path(d) / 'bad.avsnap'
            bad.write_text(json.dumps({'schema_version': 1, 'anchor': 123, 'moving': 'x', 'matrix': np.eye(4).tolist()}))
            with self.assertRaises(ValueError):
                AlignmentProject.load(bad)

    def test_viewport_combined_section_plane_and_camera_preservation(self):
        vp = CloudViewport()
        anchor = _cloud(np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]))
        moving = _cloud(np.array([[20.0, 0.0, 0.0], [30.0, 0.0, 0.0]]))
        vp.clip.setCurrentIndex(1)  # Section X
        vp.slice.setValue(50)
        bound = vp.compute_section_bound(np.asarray(anchor.points), np.asarray(moving.points))
        # Combined X range is [0, 30], 50% must be 15.0 (shared for both clouds)
        self.assertAlmostEqual(bound, 15.0)

        # set_clouds should only call set_camera when datasets change
        with patch.object(vp, 'set_camera') as mock_cam:
            vp.set_clouds(anchor, moving, np.eye(4))
            self.assertEqual(mock_cam.call_count, 1)
            t = np.eye(4)
            t[0, 3] = 1.0
            vp.set_clouds(anchor, moving, t)
            self.assertEqual(mock_cam.call_count, 1)

    def test_export_job_verifies_sources_before_overwriting_destination(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.ply', Path(d) / 'b.ply'
            pc = _cloud(np.random.default_rng(1).uniform(size=(100, 3)))
            o3d.io.write_point_cloud(str(a), pc)
            o3d.io.write_point_cloud(str(b), pc)
            dest = Path(d) / 'existing.ply'
            dest.write_text('keep-me')
            p = AlignmentProject(
                anchor=str(a),
                moving=str(b),
                report={'status': 'Validated'},
                fingerprints={'anchor': fingerprint(a), 'moving': fingerprint(b)},
            )
            p.approve()
            io = IOManager()
            # Mutate moving file right before commit via spy
            real_export = io.export_dataset

            def mutate_then_export(*args, **kwargs):
                b.write_text('mutated-mid-export')
                return real_export(*args, **kwargs)

            errors = []
            with patch.object(io, 'export_dataset', side_effect=mutate_then_export):
                job = ExportJob(p, io, pc, str(dest))
                job.error.connect(errors.append)
                job.run()
                app.processEvents()
            self.assertTrue(errors)
            self.assertEqual(dest.read_text(), 'keep-me')

    def test_gui_helpers_and_no_spurious_initial_undo(self):
        self.assertEqual(_append_filter_extension('/tmp/out', 'PLY (*.ply)', '.ply'), '/tmp/out.ply')
        self.assertEqual(_append_filter_extension('/tmp/out.las', 'PLY (*.ply)', '.ply'), '/tmp/out.las')
        self.assertEqual(len(_truncate_status('x' * 200, limit=50)), 50)
        with tempfile.TemporaryDirectory() as d:
            a, b = str(Path(d) / 'a.ply'), str(Path(d) / 'b.ply')
            pc = _cloud(np.random.default_rng(3).uniform(size=(100, 3)))
            o3d.io.write_point_cloud(a, pc)
            o3d.io.write_point_cloud(b, pc)
            w = MainWindow()
            w.project.anchor = a
            w.project.moving = b
            report = {'status': 'Validated', 'source_overlap': 1.0, 'target_overlap': 1.0, 'median_residual_m': 0.0, 'p95_residual_m': 0.0}
            w.handle_finished({
                'anchor': pc, 'moving': pc, 'matrix': np.eye(4), 'report': report,
                'fingerprints': {'anchor': fingerprint(a), 'moving': fingerprint(b)},
                'operation': 'restore',
            })
            self.assertEqual(len(w.project.history), 0)
            self.assertFalse(w.undo_button.isEnabled())
            w.close()
