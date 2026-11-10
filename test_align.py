import sys
import os

# Add the project root to sys.path so we can import src modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.io_manager import IOManager
import open3d as o3d
import numpy as np

def analyze_datasets():
    manager = IOManager()
    
    print("Loading IFC...")
    target = manager.load_dataset("C:/Users/callen/Downloads/Bergdorf Goodman MTM Corner.ifc")
    target_extent = max(target.get_axis_aligned_bounding_box().get_extent())
    print(f"Target (IFC) Extent: {target_extent}")
    print(f"Target (IFC) BBox: {target.get_axis_aligned_bounding_box()}")
    
    print("\nLoading E57 (via pye57 extraction process, this may take a bit)...")
    source = manager.load_dataset("C:/Users/callen/Downloads/2026-02-24_Mens.e57")
    source_extent = max(source.get_axis_aligned_bounding_box().get_extent())
    print(f"Source (E57) Extent: {source_extent}")
    print(f"Source (E57) BBox: {source.get_axis_aligned_bounding_box()}")
    
    # Calculate ratio
    ratio = source_extent / target_extent if target_extent > 0 else 0
    print(f"\nScale Ratio (Source/Target): {ratio}")

if __name__ == "__main__":
    analyze_datasets()
