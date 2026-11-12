"""Dataset ingestion, bounded in-memory caching and verified atomic exports."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from collections import OrderedDict
import numpy as np
import open3d as o3d
from src.logger_config import log
from src.transforms import rigid_matrix


class IOManager:
    def __init__(self, cache_bytes=512 * 1024**2, max_points=20_000_000):
        self.loaded_meshes = {}
        self.metadata = {}
        self.attributes = {}
        self.cache = OrderedDict()
        self.cache_bytes = cache_bytes
        self.max_points = max_points
        self.cache_hits = 0
        self.cancelled = lambda: False

    def clear_cache(self):
        self.cache.clear(); self.loaded_meshes.clear(); self.attributes.clear(); self.metadata.clear()

    def load_dataset(self, file_path, is_reference=False):
        file_path = str(Path(file_path).resolve())
        ext = Path(file_path).suffix.lower()
        if ext in {'.rcs', '.rcp', '.rvt'}:
            raise ValueError(f'Native {ext.upper()} reading is unavailable. Convert with Autodesk to E57/LAS or IFC first.')
        stat = os.stat(file_path)
        key = (file_path, stat.st_size, stat.st_mtime_ns)
        if key in self.cache:
            self.cache.move_to_end(key); self.cache_hits += 1
            return copy.deepcopy(self.cache[key][0])
        if ext in {'.ply', '.pcd', '.pts', '.xyz'}:
            pcd = o3d.io.read_point_cloud(file_path)
        elif ext in {'.las', '.laz'}:
            pcd = self._load_las(file_path)
        elif ext == '.e57':
            pcd = self._load_e57(file_path)
        elif ext == '.ifc':
            pcd = self._load_ifc(file_path)
        else:
            raise ValueError(f'Unsupported input format: {ext}')
        points = np.asarray(pcd.points)
        if len(points) == 0 or not np.isfinite(points).all():
            raise ValueError('Dataset must contain finite, nonempty XYZ coordinates.')
        self._check_count(len(points))
        self.metadata.setdefault(file_path, {}).update({'point_count': len(points), 'units': 'metres assumed for point clouds; IFC converted to SI', 'path': file_path})
        size = sum(np.asarray(a).nbytes for a in [pcd.points, pcd.colors, pcd.normals])
        # Drop obsolete versions and evict least recently used full clouds.
        for old in list(self.cache):
            if old[0] == file_path:
                self.cache.pop(old)
        while self.cache and sum(item[1] for item in self.cache.values()) + size > self.cache_bytes:
            self.cache.popitem(last=False)
        if size <= self.cache_bytes:
            self.cache[key] = (copy.deepcopy(pcd), size)
        return pcd

    def _check_count(self, count):
        if count > self.max_points:
            raise ValueError(f'{count:,} points exceed the interactive limit ({self.max_points:,}). Tile or downsample a copy first; originals are unchanged.')

    def _load_las(self, file_path):
        import laspy
        with laspy.open(file_path) as reader:
            self._check_count(reader.header.point_count)
            points = np.empty((reader.header.point_count, 3))
            has_color = 'red' in set(reader.header.point_format.dimension_names)
            colors = np.empty_like(points) if has_color else None
            offset = 0
            for chunk in reader.chunk_iterator(250_000):
                end = offset + len(chunk)
                points[offset:end] = np.column_stack([chunk.x, chunk.y, chunk.z])
                if has_color:
                    colors[offset:end] = np.column_stack([chunk.red, chunk.green, chunk.blue]) / 65535
                offset = end
            self.metadata[file_path] = {'crs': str(reader.header.parse_crs()), 'format': 'LAS/LAZ; original attributes retained on native export'}
        pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
        if colors is not None:
            pcd.colors = o3d.utility.Vector3dVector(colors)
        return pcd

    def _worker(self, args):
        command = [sys.executable, '--e57-worker'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'src.e57_worker']
        environment = os.environ.copy()
        root = str(Path(__file__).resolve().parent.parent)
        environment['PYTHONPATH'] = root + os.pathsep + environment.get('PYTHONPATH', '')
        import time
        started = time.monotonic()
        process = subprocess.Popen(command + list(map(str,args)),env=environment,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            while True:
                if self.cancelled():
                    raise InterruptedError('E57 operation cancelled.')
                if time.monotonic()-started > 3600:
                    raise TimeoutError('E57 operation exceeded one hour.')
                try:
                    stdout,stderr = process.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                raise RuntimeError('E57 operation failed: '+stderr[-3000:])
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()


    def _load_e57(self, file_path):
        # Read scan headers before allocating disk-backed extraction arrays.
        # Import pye57 only in the isolated process to avoid Qt/Xerces conflicts.
        with tempfile.TemporaryDirectory(prefix='av-snap-e57-') as directory:
            self._worker(['extract', file_path, directory, self.max_points])
            folder = Path(directory)
            metadata = json.loads((folder/'metadata.json').read_text())
            self._check_count(metadata['count'])
            n = metadata['count']
            pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.load(folder/'points.npy', mmap_mode='r+')[:n]))
            if metadata['has_colors']:
                pcd.colors = o3d.utility.Vector3dVector(np.load(folder/'colors.npy', mmap_mode='r+')[:n])
            self.metadata[file_path] = metadata
            self.attributes[file_path] = {'intensity': np.array(np.load(folder/'intensity.npy', mmap_mode='r+')[:n])}
            return pcd

    def _load_ifc(self, file_path):
        import ifcopenshell
        import ifcopenshell.geom
        model = ifcopenshell.open(file_path)
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        iterator = ifcopenshell.geom.iterator(settings, model, min(4, os.cpu_count() or 1))
        if not iterator.initialize():
            raise ValueError('IFC contains no tessellatable geometry.')
        vertices, faces, count = [], [], 0
        while True:
            shape = iterator.get()
            v = np.asarray(shape.geometry.verts).reshape(-1,3)
            f = np.asarray(shape.geometry.faces).reshape(-1,3)
            if len(f):
                self._check_count(count + len(v))
                vertices.append(v.copy()); faces.append(f.copy() + count); count += len(v)
            if not iterator.next():
                break
        if not vertices:
            raise ValueError('IFC contains no triangles.')
        mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.vstack(vertices)), o3d.utility.Vector3iVector(np.vstack(faces)))
        mesh.compute_vertex_normals()
        # Surface-area dependent sample budget, bounded for interactive registration.
        budget = int(np.clip(mesh.get_surface_area() / .03**2, 10_000, 250_000))
        pcd = mesh.sample_points_uniformly(number_of_points=budget)
        pcd.normals = o3d.utility.Vector3dVector()
        pcd.paint_uniform_color([.65,.65,.65])
        self.metadata[file_path] = {'sample_count': budget, 'sample_surface_area_m2': mesh.get_surface_area()}
        return pcd

    def preprocess_point_cloud(self, pcd, voxel_size=.05, noise_filter=True):
        if voxel_size <= 0:
            raise ValueError('Voxel size must be positive.')
        result = pcd.voxel_down_sample(voxel_size)
        if noise_filter and len(result.points) > 30:
            result, _ = result.remove_statistical_outlier(nb_neighbors=20, std_ratio=2)
        if len(result.points) < 6:
            raise ValueError('Insufficient geometry after preprocessing.')
        result.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size*3, max_nn=40))
        return result

    def _export_ifc_safe(self, source, destination, matrix):
        from src.ifc_export import export_ifc
        return export_ifc(source, destination, matrix)

    def export_dataset(self, pcd, file_path, original_file_path=None, transform_matrix=None):
        destination = Path(file_path).resolve()
        source = Path(original_file_path).resolve() if original_file_path else None
        if source and (source == destination or (destination.exists() and os.path.samefile(source,destination))):
            raise ValueError('Export must not overwrite the original source.')
        ext = destination.suffix.lower()
        if ext == '.ifc':
            if source is None or source.suffix.lower() != '.ifc' or transform_matrix is None:
                raise ValueError('Native IFC export requires the original IFC and approved rigid transform.')
            return self._export_ifc_safe(source, destination, transform_matrix)
        if ext not in {'.ply','.pcd','.xyz','.e57','.las','.laz'}:
            raise ValueError(f'Unsupported export format: {ext}')
        fd, tmp = tempfile.mkstemp(prefix='.av-snap-', suffix=ext, dir=destination.parent)
        os.close(fd)
        try:
            if ext == '.e57':
                if source is None or source.suffix.lower() != '.e57' or transform_matrix is None:
                    raise ValueError('E57 export requires an original E57 to preserve scan structure and attributes. Use PLY for other inputs.')
                with tempfile.TemporaryDirectory(prefix='av-snap-transform-') as d:
                    matrix = Path(d)/'matrix.npy'
                    np.save(matrix, rigid_matrix(transform_matrix))
                    self._worker(['transform', source, tmp, matrix])
            elif ext in {'.las','.laz'}:
                if source is None or source.suffix.lower() not in {'.las','.laz'} or transform_matrix is None:
                    raise ValueError('Native LAS/LAZ export requires an original LAS/LAZ and rigid transform.')
                self._export_las(source, tmp, transform_matrix)
            else:
                if not o3d.io.write_point_cloud(tmp, pcd):
                    raise RuntimeError('Point-cloud writer failed.')
                check = o3d.io.read_point_cloud(tmp)
                if len(check.points) != len(pcd.points) or not np.allclose(check.points, pcd.points, atol=1e-5, rtol=0):
                    raise RuntimeError('Point-cloud precision failed roundtrip validation. Choose binary PLY for large world coordinates.')
                if ext != '.xyz' and pcd.has_colors() and (not check.has_colors() or not np.allclose(check.colors,pcd.colors,atol=1/255,rtol=0)):
                    raise RuntimeError('Point colors failed roundtrip validation.')
            os.replace(tmp, destination)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _export_las(source, destination, matrix):
        import laspy
        matrix = rigid_matrix(matrix)
        with laspy.open(source) as reader:
            if 'wavepacket_offset' in set(reader.header.point_format.dimension_names) and not np.allclose(matrix[:3,:3],np.eye(3)):
                raise ValueError('Rotating LAS waveform vectors is not supported; convert a copy to a non-waveform LAS first.')
            header = copy.deepcopy(reader.header)
            header.offsets = matrix[:3,:3] @ header.offsets + matrix[:3,3]
            with laspy.open(destination, mode='w', header=header) as writer:
                for chunk in reader.chunk_iterator(250_000):
                    xyz = np.column_stack([chunk.x,chunk.y,chunk.z]) @ matrix[:3,:3].T + matrix[:3,3]
                    chunk.change_scaling(scales=header.scales, offsets=header.offsets)
                    chunk.x, chunk.y, chunk.z = xyz.T
                    writer.write_points(chunk)
        with laspy.open(source) as reader, laspy.open(destination) as check:
            if reader.header.point_count != check.header.point_count:
                raise RuntimeError('LAS point count changed.')
            for a,b in zip(reader.chunk_iterator(250_000), check.chunk_iterator(250_000)):
                expected = np.column_stack([a.x,a.y,a.z]) @ matrix[:3,:3].T + matrix[:3,3]
                if not np.allclose(expected, np.column_stack([b.x,b.y,b.z]), atol=max(check.header.scales)*.51, rtol=0):
                    raise RuntimeError('LAS coordinates failed validation.')
                for name in a.point_format.dimension_names:
                    if name not in {'X','Y','Z'} and not np.array_equal(a[name],b[name]):
                        raise RuntimeError(f'LAS attribute {name} changed.')
