import os, numpy as np, ifcopenshell
from src.io_manager import IOManager

# Paths (adjust if needed)
original_ifc = r"C:/Users/ChristopherAllen/Downloads/24014 - 07242026-Stag Lodge_Architectural coordination file.ifc"
export_ifc = r"C:/Users/ChristopherAllen/Downloads/verify_aligned.ifc"

# Dummy identity transform (no change)
identity = np.identity(4)

# Ensure output directory exists
os.makedirs(os.path.dirname(export_ifc), exist_ok=True)

# Create IOManager instance (no actual point cloud needed for IFC export)
manager = IOManager()
# For export_dataset we need a point cloud; we can pass a dummy empty point cloud (Open3D)
import open3d as o3d
pcd = o3d.geometry.PointCloud()
# Export using the updated method
manager.export_dataset(pcd, export_ifc, original_file_path=original_ifc, transform_matrix=identity)

# Load exported IFC and count products
f = ifcopenshell.open(export_ifc)
products = f.by_type('IfcProduct')
print('Exported IFC product count:', len(products))
