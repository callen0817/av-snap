import sys
import multiprocessing
import ifcopenshell
import ifcopenshell.geom
import numpy as np
import open3d as o3d
import traceback

def extract_ifc():
    print("Loading IFC...")
    f = ifcopenshell.open('C:/Users/callen/Downloads/Bergdorf Goodman MTM Corner.ifc')
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    print("Initializing Iterator...")
    iterator = ifcopenshell.geom.iterator(settings, f, multiprocessing.cpu_count())
    if not iterator.initialize():
        print("Failed to initialize iterator")
        return
        
    master_verts = []
    master_faces = []
    vertex_offset = 0
    
    print("Extracting Geometry...")
    while True:
        try:
            shape = iterator.get()
            geom = shape.geometry
            
            verts = np.array(geom.verts).reshape(-1, 3)
            faces = np.array(geom.faces).reshape(-1, 3)
            
            if len(verts) > 0 and len(faces) > 0:
                master_verts.append(verts)
                # Offset the face indices by the total number of vertices added so far
                master_faces.append(faces + vertex_offset)
                vertex_offset += len(verts)
        except Exception as e:
            print(f"Error extracting shape: {e}")
            
        if not iterator.next():
            break
            
    print(f"Compiling {len(master_verts)} elements...")
    
    if not master_verts:
        print("No geometry found!")
        return
        
    all_verts = np.vstack(master_verts)
    all_faces = np.vstack(master_faces)
    
    print(f"Total Vertices: {len(all_verts)}")
    print(f"Total Faces: {len(all_faces)}")
    
    print("Building Open3D Mesh...")
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(all_verts)
    mesh.triangles = o3d.utility.Vector3iVector(all_faces)
    
    print("Sampling to Point Cloud...")
    # Sample 100,000 points uniformly from the faces
    pcd = mesh.sample_points_uniformly(number_of_points=100000)
    print(f"Generated Point Cloud with {len(pcd.points)} points.")

if __name__ == "__main__":
    extract_ifc()
