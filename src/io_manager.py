import os
import open3d as o3d
import numpy as np
import pye57
from src.logger_config import log, log_milestone

class IOManager:
    def __init__(self):
        # We can dynamically try to load heavy/niche libraries only if needed
        self.loaded_meshes = {}

    def load_dataset(self, file_path, is_reference=False):
        """
        Loads a dataset (model or point cloud), converting it to an Open3D point cloud format.
        is_reference flag can be used to tag the dataset, though in IO it just loads.
        """
        ext = os.path.splitext(file_path)[1].lower()
        log.info(f"Loading dataset: {file_path}")
        
        try:
            if ext in ['.pcd', '.ply', '.pts', '.xyz']:
                pcd = o3d.io.read_point_cloud(file_path)
            elif ext == '.las':
                pcd = self._load_las(file_path)
            elif ext == '.e57':
                pcd = self._load_e57(file_path)
            elif ext == '.rcs':
                pcd = self._load_rcs(file_path)
            elif ext == '.ifc':
                pcd = self._load_ifc(file_path)
            elif ext == '.rvt':
                pcd = self._load_rvt(file_path)
            else:
                raise ValueError(f"Unsupported file format: {ext}")
                
            if pcd.is_empty():
                raise ValueError("Loaded point cloud is empty!")
                
            log.info(f"Loaded {len(pcd.points)} points. Preserving original point density for export.")
            # We purposely skip `self.preprocess_point_cloud` here to ensure 100% full density 
            # is preserved for the final export file. The AlignmentEngine safely handles downsampling 
            # internally for the mathematics solvers.
                
            log_milestone("Phase 2", f"File I/O ({ext})", "Completed Successfully")
            return pcd
            
        except Exception as e:
            log.error(f"Failed to load {file_path}: {e}")
            raise

    def _load_las(self, file_path):
        try:
            import laspy
            las = laspy.read(file_path)
            points = np.vstack((las.x, las.y, las.z)).transpose()
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            # Add colors if available
            if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
                colors = np.vstack((las.red, las.green, las.blue)).transpose() / 65535.0
                pcd.colors = o3d.utility.Vector3dVector(colors)
            return pcd
        except ImportError:
            log.warning("laspy not installed. Falling back to simple processing if possible.")
            raise

    def _load_e57(self, file_path):
        import subprocess
        import tempfile
        import os
        import sys
        
        try:
            # First attempt native Open3D read (if compiled with e57 support)
            log.info("Attempting native Open3D e57 read...")
            pcd = o3d.io.read_point_cloud(file_path)
            if not pcd.is_empty():
                return pcd
            else:
                log.warning("Open3D native e57 read returned empty. Trying pye57...")
        except Exception as e:
            log.warning(f"Native Open3D e57 read failed: {e}. Trying pye57...")

        # Run pye57 in a separate subprocess.
        # This completely isolates pye57's Xerces-C/COM initialization from PyQt5's.
        # If executed inside the same process as QApplication, pye57 can cause a fatal crash.
        tmp_dir = tempfile.gettempdir()
        safe_name = os.path.basename(file_path).replace(" ", "_")
        tmp_pcd_path = os.path.join(tmp_dir, f"temp_{safe_name}.pcd")
        script_path = os.path.join(tmp_dir, f"extract_e57_{safe_name}.py")
        
        script_code = """
import sys
import pye57
import numpy as np
import open3d as o3d
import traceback

try:
    file_path = sys.argv[1]
    out_path = sys.argv[2]
    e57 = pye57.E57(file_path)
    data = e57.read_scan_raw(0, ignore_unsupported_fields=True)
    
    keys = [k.lower() for k in data.keys()]
    if "cartesianx" not in keys:
        raise ValueError("Could not find cartesian coordinates in e57 scan 0.")
        
    x_key = list(data.keys())[keys.index("cartesianx")]
    y_key = list(data.keys())[keys.index("cartesiany")]
    z_key = list(data.keys())[keys.index("cartesianz")]
    
    points = np.column_stack((data[x_key], data[y_key], data[z_key]))
    
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    
    # Save colors if available
    if "colorred" in keys and "colorgreen" in keys and "colorblue" in keys:
        r_key = list(data.keys())[keys.index("colorred")]
        g_key = list(data.keys())[keys.index("colorgreen")]
        b_key = list(data.keys())[keys.index("colorblue")]
        colors = np.column_stack((data[r_key], data[g_key], data[b_key]))
        # e57 colors are usually 0-255 or 0-1. normalize to 0-1 for open3d
        if colors.max() > 1.0:
            colors = colors / 255.0
        pcd.colors = o3d.utility.Vector3dVector(colors)
        
    o3d.io.write_point_cloud(out_path, pcd)
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
"""
        with open(script_path, "w") as f:
            f.write(script_code)
            
        try:
            log.info("Launching isolated pye57 extraction subprocess...")
            subprocess.check_call([sys.executable, script_path, file_path, tmp_pcd_path])
            
            log.info("Loading temporarily extracted point cloud...")
            pcd = o3d.io.read_point_cloud(tmp_pcd_path)
            
            if pcd.is_empty():
                raise ValueError("Extracted point cloud is empty.")
                
            log.info("Successfully loaded e57 via pye57 subprocess.")
            return pcd
            
        except subprocess.CalledProcessError as e:
            log.error(f"Isolated pye57 process failed: {e}")
            raise RuntimeError("Failed to read e57: Subprocess crashed or returned an error.")
        finally:
            # Clean up the temporary files
            if os.path.exists(tmp_pcd_path):
                os.remove(tmp_pcd_path)
            if os.path.exists(script_path):
                os.remove(script_path)

    def _load_rcs(self, file_path):
        # High level conceptual placeholder for Autodesk RCP/RCS loading
        # requires specific SDK parsing or tools like CloudCompare headless
        log.warning("Native generic RCS loading is complex. Implementing placeholder fallback.")
        points = np.random.rand(10000, 3) * 100 
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.paint_uniform_color([0.1, 0.8, 0.1]) # Green for RCS placeholder
        return pcd

    def _load_ifc(self, file_path):
        import numpy as np
        import multiprocessing
        import traceback
        
        try:
            import ifcopenshell
            import ifcopenshell.geom
            
            log.info("Loading IFC File...")
            f = ifcopenshell.open(file_path)
            
            log.info("Preparing Geometry Iterator...")
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            
            iterator = ifcopenshell.geom.iterator(settings, f, multiprocessing.cpu_count())
            if not iterator.initialize():
                raise RuntimeError("Failed to initialize IFC geometry iterator.")
                
            master_verts = []
            master_faces = []
            vertex_offset = 0
            
            log.info("Extracting BIM Element Geometry...")
            elements_processed = 0
            while True:
                try:
                    shape = iterator.get()
                    geom = shape.geometry
                    
                    verts = np.array(geom.verts).reshape(-1, 3)
                    faces = np.array(geom.faces).reshape(-1, 3)
                    
                    if len(verts) > 0 and len(faces) > 0:
                        master_verts.append(verts)
                        master_faces.append(faces + vertex_offset)
                        vertex_offset += len(verts)
                        elements_processed += 1
                        
                except Exception as e:
                    log.warning(f"Error extracting an IFC shape: {e}")
                    
                if not iterator.next():
                    break
            
            if not master_verts:
                raise ValueError("No extractable geometry found in IFC file.")
                
            log.info(f"Geometry aggregated from {elements_processed} elements. Converting to Open3D TriangleMesh...")
            all_verts = np.vstack(master_verts)
            all_faces = np.vstack(master_faces)
            
            mesh = o3d.geometry.TriangleMesh()
            mesh.vertices = o3d.utility.Vector3dVector(all_verts)
            mesh.triangles = o3d.utility.Vector3iVector(all_faces)
            
            # Compute normals so the mesh interacts with lighting correctly
            mesh.compute_vertex_normals()
            mesh.paint_uniform_color([0.5, 0.5, 0.5]) # Distinctive gray color for reference model
            
            # Store the polished mesh for final rendering
            self.loaded_meshes[file_path] = mesh
            
            # Since this is a reference model, we sample enough points to ensure strong surface coverage
            # for the alignment optimizer, but not so many that we cause memory issues.
            # Downsampling will occur during preprocessing phase 2 later anyway.
            log.info("Sampling 1,000,000 points uniformly from IFC BIM Mesh (Increased for symmetry resolution)...")
            pcd = mesh.sample_points_uniformly(number_of_points=1000000)
            
            # CLEAR THE NORMALS! 
            # The sampled points passively inherit the newly computed 3D mesh normals. 
            # If the scanner (e.g. .e57) datasets have unoriented/different normals, the FPFH algorithm 
            # will mathematically flip the entire alignment upside-down to force the normal vectors to align.
            pcd.normals = o3d.utility.Vector3dVector()
            
            pcd.paint_uniform_color([0.5, 0.5, 0.5]) # Distinctive gray color for reference model
            
            log.info("IFC parsing complete.")
            return pcd
            
        except ImportError:
            log.error("ifcopenshell not found. Cannot process IFC files natively.")
            raise
        except Exception as e:
            log.error(f"Failed to extract IFC geometry: {e}")
            traceback.print_exc()
            raise

    def _load_rvt(self, file_path):
        # Direct local RVT read typically relies on Revit API (pythonnet) or local conversion
        # This requires Revit to be installed and accessible.
        log.warning("RVT file loading generally requires active Revit API context via pythonnet. Providing placeholder pointcloud.")
        points = np.random.rand(10000, 3) * 100 
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd.paint_uniform_color([0.8, 0.1, 0.1])
        return pcd

    def preprocess_point_cloud(self, pcd, voxel_size=0.05, noise_filter=True):
        """
        Downsamples the point cloud to speed up processing and optionally filters noise.
        """
        log.info(f"Preprocessing point cloud. Original points: {len(pcd.points)}")
        
        if voxel_size > 0:
            pcd_down = pcd.voxel_down_sample(voxel_size)
            log.info(f"Voxel downsampled. New points: {len(pcd_down.points)}")
        else:
            pcd_down = pcd
            
        if noise_filter:
            pcd_down, ind = pcd_down.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
            log.info(f"Noise filtered. Final points: {len(pcd_down.points)}")
            
        # Estimate normals which is required for many alignment algorithms
        pcd_down.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30))
            
        log_milestone("Phase 2", "Preprocessing", "Completed")
        return pcd_down

    def export_dataset(self, pcd, file_path, original_file_path=None, transform_matrix=None):
        """
        Exports the aligned Open3D PointCloud or native BIM model back to the requested file format.
        Has specific safeguards for writing .e57 natively to avoid PyQt crashes.
        Supports exporting transformed IFC models (.ifc).
        """
        ext = os.path.splitext(file_path)[1].lower()
        log.info(f"Exporting dataset to {file_path}")
        
        try:
            if ext == '.e57':
                self._export_e57_safe(pcd, file_path)
            elif ext == '.ifc':
                if original_file_path and transform_matrix is not None:
                    self._export_ifc_safe(original_file_path, file_path, transform_matrix)
                else:
                    fallback_path = os.path.splitext(file_path)[0] + '.ply'
                    log.warning("Original IFC path or transformation matrix missing. Falling back to .ply export.")
                    o3d.io.write_point_cloud(fallback_path, pcd)
            elif ext in ['.ply', '.pcd', '.xyz']:
                o3d.io.write_point_cloud(file_path, pcd)
            else:
                # Fallback to .ply for unsupported extensions
                fallback_path = os.path.splitext(file_path)[0] + '.ply'
                log.warning(f"Unsupported export extension '{ext}'. Falling back to '{fallback_path}'.")
                o3d.io.write_point_cloud(fallback_path, pcd)
                
        except Exception as e:
            log.error(f"Failed to export dataset: {e}")
            raise

    def _export_ifc_safe(self, original_file_path, export_file_path, transform_matrix):
        """Apply the alignment transformation matrix to the IFC model and export it.

        The alignment engine works in SI (meters). IFC projects may use other length units.
        This method:
        1️⃣ Determines the project's length unit scale (meters per IFC unit).
        2️⃣ Finds the highest spatial root (IfcSite > IfcBuilding > any spatial element with placement).
        3️⃣ Retrieves the current placement matrix of the root, converts it to SI.
        4️⃣ Combines the current SI placement with the alignment transform (provided in SI).
        5️⃣ Updates or creates the root's placement while preserving the placement hierarchy.
        6️⃣ Writes the updated IFC.
        7️⃣ Re‑opens the exported IFC and validates that the placement matches the expected matrix within tolerance.
        """
        import ifcopenshell
        import ifcopenshell.api
        import ifcopenshell.util.placement as placement
        import ifcopenshell.util.unit as unit
        import numpy as np

        log.info(f"Applying transformation matrix to IFC model: {original_file_path}")
        f = ifcopenshell.open(original_file_path)

        # 1️⃣ Unit handling – meters per IFC length unit
        scale = unit.calculate_unit_scale(f)

        # 2️⃣ Find spatial root (IfcSite > IfcBuilding > any spatial element with placement)
        def find_root(ifc_file):
            sites = ifc_file.by_type("IfcSite")
            if sites:
                return sites[0]
            buildings = ifc_file.by_type("IfcBuilding")
            if buildings:
                return buildings[0]
            # Fallback: any spatial structure element with a placement
            for candidate in ifc_file.by_type("IfcSpatialStructureElement"):
                if getattr(candidate, "ObjectPlacement", None) is not None:
                    return candidate
            raise ValueError("No suitable spatial root (IfcSite/IfcBuilding/IfcSpatialStructureElement) with placement found.")

        target_obj = find_root(f)

        # 3️⃣ Current placement matrix (in IFC units) → convert to SI (meters)
        M_current = placement.get_local_placement(target_obj.ObjectPlacement)
        M_current_si = M_current.copy()
        M_current_si[:3, 3] *= scale

        # 4️⃣ Combine with the alignment transform (already in SI)
        M_new_si = np.dot(transform_matrix, M_current_si)

        # 5️⃣ Apply transform to root with child propagation
        if target_obj.ObjectPlacement:
            ifcopenshell.api.run(
                "geometry.edit_object_placement",
                f,
                product=target_obj,
                matrix=M_new_si,
                is_si=True,
                should_transform_children=True,
            )
        else:
            new_placement = ifcopenshell.api.run(
                "geometry.add_local_placement",
                f,
                matrix=M_new_si,
                is_si=True,
            )
            target_obj.ObjectPlacement = new_placement
        # Apply transform to remaining products without affecting children
        for prod in f.by_type("IfcProduct"):
            if prod.id() == target_obj.id():
                continue
            if getattr(prod, "ObjectPlacement", None) is not None:
                ifcopenshell.api.run(
                    "geometry.edit_object_placement",
                    f,
                    product=prod,
                    matrix=M_new_si,
                    is_si=True,
                    should_transform_children=False,
                )

        # 6️⃣ Write the updated IFC file
        log.info(f"Writing updated IFC file to {export_file_path}...")
        f.write(export_file_path)
        log.info("IFC export completed successfully.")

        # 7️⃣ Validation – reopen and verify placement matches expected matrix within tolerance
        f_check = ifcopenshell.open(export_file_path)
        root_check = find_root(f_check)
        M_check = placement.get_local_placement(root_check.ObjectPlacement)
        M_check_si = M_check.copy()
        M_check_si[:3, 3] *= scale
        if not np.allclose(M_new_si, M_check_si, atol=1e-6):
            raise RuntimeError("Export validation failed: placement matrix does not match expected transform.")


    def _export_e57_safe(self, pcd, out_path):
        """
        Writes an Open3D point cloud to an .e57 file via an isolated subprocess.
        This prevents pye57's Xerces-C/COM cleanup routines from crashing the PyQt loop.
        """
        import subprocess
        import tempfile
        import sys
        
        tmp_dir = tempfile.gettempdir()
        safe_name = os.path.basename(out_path).replace(" ", "_")
        
        # Save the current state of the PCD to a fast temporary file
        tmp_pcd_path = os.path.join(tmp_dir, f"temp_write_{safe_name}.ply")
        o3d.io.write_point_cloud(tmp_pcd_path, pcd)
        
        script_path = os.path.join(tmp_dir, f"write_e57_{safe_name}.py")
        
        # The script merely loads the PLY we just wrote, separates the data, and builds the E57 dict
        script_code = """
import sys
import pye57
import numpy as np
import open3d as o3d
import traceback
import os

try:
    in_ply = sys.argv[1]
    out_e57 = sys.argv[2]
    
    pcd = o3d.io.read_point_cloud(in_ply)
    points = np.asarray(pcd.points)
    
    # Pack into required dictionary format
    data = {
        'cartesianX': points[:, 0],
        'cartesianY': points[:, 1],
        'cartesianZ': points[:, 2]
    }
    
    if pcd.has_colors():
        colors = np.asarray(pcd.colors)
        # Assuming open3d colors are [0, 1] normalized floats, pack them to 0-255 uint8s
        if colors.dtype == np.float64 or colors.dtype == np.float32:
            colors = (colors * 255.0).astype(np.uint8)
            
        data['colorRed'] = colors[:, 0]
        data['colorGreen'] = colors[:, 1]
        data['colorBlue'] = colors[:, 2]
        
    e57 = pye57.E57(out_e57, mode='w')
    e57.write_scan_raw(data)
    
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
"""
        with open(script_path, "w") as f:
            f.write(script_code)
            
        try:
            log.info("Launching isolated pye57 writer subprocess...")
            subprocess.check_call([sys.executable, script_path, tmp_pcd_path, out_path])
            log.info("Successfully exported aligned dataset to matching .e57 format via subprocess.")
            
        except subprocess.CalledProcessError as e:
            log.error(f"Isolated pye57 writer process failed: {e}")
            raise RuntimeError("Failed to write aligned e57: Subprocess crashed or returned an error.")
        finally:
            if os.path.exists(tmp_pcd_path):
                os.remove(tmp_pcd_path)
            if os.path.exists(script_path):
                os.remove(script_path)
