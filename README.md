# AV Snap

**Automated 3D Point Cloud and BIM Alignment Tool**

AV Snap is a high-performance desktop application built with Python, PyQt5, Open3D, and IfcOpenShell. It performs automated, rigid-body 3D registration between terrestrial laser scans (E57, PLY, LAS) and Building Information Models (IFC), allowing architects, BIM managers, and reality-capture professionals to align coordinating models without manual guesswork.

---

## Features

- **Automated Multi-Stage Alignment Pipeline**:
  - **Center-of-Mass & PCA Coarse Registration**: Aligns geometric centroids and principal axes.
  - **RANSAC Global Registration**: Matches planar architectural features and dominant orientations across noisy, partial scans.
  - **Generalized ICP (GICP)**: Precision fine alignment snapping wall planes, slabs, and structural elements into exact millimeter-scale coincidence.
- **Native BIM Preservation**:
  - Treats IFC models as first-class BIM objects rather than lossy mesh conversions.
  - Preserves 100% of IFC metadata: element GUIDs, classifications, property sets, materials, and spatial relationships.
  - Computes and bakes the rigid transformation matrix directly into the IFC coordinate system using `IfcLocalPlacement`.
  - Automatically handles project length unit conversions (millimeters, meters, inches, feet).
- **Scan File Support**:
  - High-capacity loading of `.e57` point clouds using isolated subprocess extraction to prevent C++/Xerces crashes.
  - Support for `.ply`, `.las`, `.pcd`, and `.xyz`.
- **Interactive PyQt5 GUI**:
  - Visual status logging and milestone indicators.
  - Real-time 3D viewport for reviewing overlay before export.
  - Interactive *Save As* dialog with non-destructive re-export.
- **Full Engineering History & Design Documentation**:
  - Complete Antigravity conversation history, architectural decisions, and verification scripts included under `docs/antigravity-history/`.

---

## Architecture Overview

```
                          +------------------------+
                          |   AV Snap GUI Window   |
                          +------------------------+
                                      |
                 +--------------------+--------------------+
                 |                                         |
                 v                                         v
       +--------------------+                    +--------------------+
       |   Anchor Dataset   |                    |   Moving Dataset   |
       | (.e57 Point Cloud) |                    |    (.ifc Model)    |
       +--------------------+                    +--------------------+
                 |                                         |
                 | (pye57 subprocess)                      | (IfcOpenShell)
                 v                                         v
       +--------------------+                    +--------------------+
       |  Point Cloud PCD   |                    | Aggregated BIM PCD |
       +--------------------+                    +--------------------+
                 \                                         /
                  \                                       /
                   v                                     v
                 +-----------------------------------------+
                 |            Alignment Engine             |
                 |  1. Voxel Downsample & Noise Filter     |
                 |  2. RANSAC Planar Coarse Registration   |
                 |  3. Generalized ICP (GICP) Refinement   |
                 +-----------------------------------------+
                                      |
                                      v
                       Canonical Transform Matrix M
                                      |
                 +--------------------+--------------------+
                 |                                         |
                 v                                         v
       +--------------------+                    +--------------------+
       | Real-time Viewport |                    | Native IFC Exporter|
       |  Overlay Rendering |                    | - Unit scale check |
       +--------------------+                    | - Root placement   |
                                                 | - Matrix validation|
                                                 +--------------------+
```

---

## Installation & Setup

### Prerequisites
- **Python**: Recommended Python 3.10 or 3.11 (64-bit).
- **Windows**: Windows 10 / 11.

### Setup Environment
```powershell
# Clone the repository
git clone https://github.com/callen0817/av-snap.git
cd av-snap

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running AV Snap
To launch the graphical user interface:
```powershell
python launch.py
```

---

## Repository Structure

```
├── launch.py                     # Entry point & dependency validator
├── requirements.txt              # Production dependency list
├── AV_Snap.spec                  # PyInstaller build spec
├── EXCLUSIONS.md                 # Specification of excluded data & local rebuild guide
├── README.md                     # Project documentation
├── ads/                          # Product marketing & video splash screen assets
├── logos/                        # Application icons and branding assets
├── src/
│   ├── alignment_engine.py       # Core registration math (RANSAC, GICP, Centroid)
│   ├── io_manager.py             # BIM & scan I/O with unit-aware placement baking
│   ├── logger_config.py          # Session logging utilities
│   └── main_gui.py               # PyQt5 graphical interface & event loop
├── docs/
│   └── antigravity-history/      # Antigravity session records & architectural plans
│       ├── conversation-transcript.md
│       ├── architectural-decisions-and-plans.md
│       ├── session-summary.md
│       ├── verify_export.py
│       └── raw/
│           ├── transcript.jsonl
│           └── transcript_full.jsonl
└── tests/
    ├── test_align.py
    ├── test_com_icp.py
    ├── test_engine.py
    └── test_ifc_extract.py
```

---

## License & Credits

Developed with Antigravity AI pair-programming assistant.
Copyright (c) 2026. All rights reserved.
