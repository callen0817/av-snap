# AV Snap: Architectural Decisions, Implementation Plans & Technical Specifications

This document outlines the architectural specifications, workflow decisions, and technical implementation details developed during the Antigravity engineering sessions for **AV Snap** (Automated 3D Point Cloud and BIM Alignment Tool).

---

## 1. Executive Summary & Core Paradigm

**AV Snap** is an automated spatial alignment engine designed to register 3D point cloud datasets (e.g., `.e57`, `.ply`, `.las`) and Building Information Modeling (BIM) files (`.ifc`) into a unified, mathematically consistent coordinate reference system.

### Core Architecture Principle: Native BIM Preservation
During the development of AV Snap, a critical workflow requirement was formalized:
> **The IFC model remains an IFC model throughout the entire alignment and export lifecycle.**
> 
> The alignment engine computes a rigid-body transformation (rotation $R \in \mathrm{SO}(3)$ and translation $T \in \mathbb{R}^3$) that places the IFC into the scan (e.g. E57) coordinate frame. The export step must **never** convert the IFC into a point cloud, mesh, or alternate geometry format (such as `.ply` or `.obj`). Instead, it persists the exact $4 \times 4$ transformation matrix directly into the IFC dataset while preserving 100% of the original BIM hierarchy, property sets, relationships, materials, and element GUIDs.

```
+------------------------------------+       +------------------------------------+
|  Anchor Dataset (.e57 Point Cloud) |       |     Moving Dataset (.ifc Model)    |
+------------------------------------+       +------------------------------------+
                  |                                             |
                  v                                             v
       [Subprocess Extraction]                         [Geometry Extraction]
       Preserve Point Density                         Aggregate BIM Geometry
                  |                                             |
                  +----------------------+----------------------+
                                         |
                                         v
                         +-------------------------------+
                         |   Alignment Engine Pipeline   |
                         |  1. Center-Match Coarse Reg   |
                         |  2. RANSAC Layout Orientation |
                         |  3. Generalized ICP (GICP)    |
                         +-------------------------------+
                                         |
                                         v
                        Authoritative Transform Matrix:
                             M_alignment in SE(3)
                                         |
                  +----------------------+----------------------+
                  |                                             |
                  v                                             v
      [Visualizer Viewport]                          [Native IFC Exporter]
   Real-time transformed IFC                      1. Detect Project Unit Scale
      overlay on Point Cloud                      2. Locate Spatial Root
                                                  3. Compute M_new_si
                                                  4. Update Placements
                                                  5. Validate Matrix Consistency
```

---

## 2. Detailed Technical Decisions & Specifications

### 2.1 Single Authoritative Transformation Matrix
* **Requirement**: There must be exactly one authoritative transformation matrix $M \in \mathrm{SE}(3)$ produced by the alignment engine (`self.transform_matrix`).
* **Enforcement**:
  * The visualizer, manual fine-tuning handles, ICP refinement, and the exporter all consume this single source of truth.
  * The exporter does not re-compute, approximate, or derive a new transform. It consumes the canonical matrix directly.

### 2.2 Spatial Placement Hierarchy & Propagation
In IFC schemas (IFC2X3, IFC4), spatial structure elements and physical building products are positioned using `IfcLocalPlacement`:
1. **Spatial Root Detection**:
   * Inspect the IFC hierarchy to find the true spatial root:
     $$\text{Target} = \text{IfcSite} \succ \text{IfcBuilding} \succ \text{IfcSpatialStructureElement}$$
   * Avoid hardcoding assumptions about object order or class names.
2. **Placement Hierarchy Preservation**:
   * If the root already possesses an `IfcLocalPlacement`, update its transform rather than deleting and replacing it. This ensures all child elements that reference it maintain valid relationship chains.
   * Root placement is updated with `should_transform_children=True`.
   * To handle files with disjointed placement trees or independent elements, the exporter also updates the placements of all `IfcProduct` instances (`should_transform_children=False`), guaranteeing that both the spatial levels and the building geometry (walls, slabs, doors, MEP) move in exact unison.

### 2.3 Unit-Consistent Coordinate Handling
* Point cloud engines, Open3D, and AV Snap's internal registration algorithms operate in SI units (meters).
* Real-world IFC projects are often authored in millimeters, inches, or US survey feet.
* **Implementation**:
  * Use `ifcopenshell.util.unit.calculate_unit_scale(f)` to extract the exact meters-per-unit scale factor:
    $$\text{scale} = \text{meters\_per\_unit}$$
  * Transform the current local placement matrix into SI meters:
    $$M_{\text{current\_si}}[:3, 3] = M_{\text{current}}[:3, 3] \times \text{scale}$$
  * Compose the alignment transform with the current SI placement:
    $$M_{\text{new\_si}} = M_{\text{alignment}} \cdot M_{\text{current\_si}}$$
  * Apply $M_{\text{new\_si}}$ with flag `is_si=True` via `ifcopenshell.api.run("geometry.edit_object_placement", ...)`.

### 2.4 Atomic, Non-Destructive Export Workflow
To support iterative refinement without cumulative transformations:
* Never mutate the in-memory IFC dataset repeatedly across exports.
* On each export:
  1. Reload the pristine original IFC from disk.
  2. Apply the canonical `self.transform_matrix`.
  3. Write the result to the destination selected by the user via the `QFileDialog.getSaveFileName` dialog.
  4. Close the file handle cleanly.

### 2.5 Strict Failure Behavior & Elimination of Point Cloud Fallback
* In earlier revisions, if an IFC export encountered missing inputs, the system fell back to saving a `.ply` point cloud.
* **Architectural Correction**: Converting an IFC to a point cloud during export was explicitly banned. If an IFC export fails or cannot locate the model or transform:
  * Stop immediately.
  * Log a clear diagnostic error.
  * Surface a modal warning to the user via `QMessageBox.critical`.
  * **Never** fall back to point cloud formats when the user requested an IFC export.

### 2.6 Post-Export Verification Routine
Immediately after writing the exported IFC to disk:
1. Re-open the written IFC file using `ifcopenshell.open(export_file_path)`.
2. Retrieve the placement of the root element using `ifcopenshell.util.placement.get_local_placement`.
3. Convert to SI and compare against $M_{\text{new\_si}}$ with numerical tolerance ($\text{atol} = 10^{-6}$):
   $$\| M_{\text{expected}} - M_{\text{written}} \|_{\infty} \le 10^{-6}$$
4. Throw a `RuntimeError` if validation fails, preventing corrupted files from silently passing.

---

## 3. Verification & Validation Protocol

To confirm spatial alignment and data integrity across CAD/BIM ecosystems:
1. **AV Snap Clean Session Reload**:
   * Close the application.
   * Open AV Snap and load the exported `_aligned.ifc` alongside the original `.e57` point cloud.
   * Verify they overlay immediately in the 3D viewport without running auto-alignment again.
2. **External BIM Viewer Verification**:
   * Open the aligned IFC in standard external viewers (e.g. BIMvision, Solibri, Autodesk Revit, BlenderBIM).
   * Verify that all building storeys, levels, walls, doors, structural columns, property sets, and GUIDs are intact.
3. **Scripted Verification**:
   * The automated check script `scratch/verify_export.py` can be run headless to assert element counts and placement validity across models.
