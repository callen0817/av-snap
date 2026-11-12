# AV Snap

Artificial Vision's local desktop scan-to-BIM alignment studio. The workflow is **Import → Align → Review → Approve → Export**. Original measurements and BIM files remain authoritative.

## Install and run

Use 64-bit Python 3.12 (tested on Linux). Windows validation is configured in CI but has not been run in this cloud task.

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip check
python launch.py
```

Launching never installs dependencies or requires an online service. An OpenGL-capable desktop is required for the embedded viewport and manual point picking. Headless development can use `QT_QPA_PLATFORM=offscreen AV_SNAP_HEADLESS=1`; this disables the viewport, not the registration engine. `python launch.py --smoke-test` checks startup and exits automatically. Set `AV_SNAP_SCREENSHOT` to choose its screenshot path.

## Using the studio

1. Import an **anchor**, which stays fixed, and a **moving** scan or model. Both datasets are loaded in a worker. Point clouds must already use metres in a compatible project coordinate frame; confirm this before alignment. IFC tessellation uses SI metres. There is no automatic CRS reprojection.
2. Choose Fast, Balanced, or Quality. Upright/yaw-only is an optional prior; full rigid rotation is the default. Automatic alignment compares coordinate, architectural yaw and feature-based candidates, then refines them with coarse-to-fine robust GICP. Input data is never scaled to improve a fit.
3. Review bidirectional overlap, median/P95 inlier residuals, competing solutions, original/aligned overlays, or color by error. Low residuals alone do not establish registration. Alternative-candidate comparisons can mark repetitive geometry **Needs Review**. Color-by-error is a sampled preview, not a survey certificate.
4. Manual picking opens Open3D windows in a separate process. Shift-click three or more matching, non-collinear points in the same order, then Q. Alternatively, enter control coordinates in the studio. Both routes compute a rigid transform and refine it. Translation/rotation adjustments rotate about the aligned cloud's centre. Undo, redo, reset and refinement revoke approval.
5. Approve the transform. **Needs Review** requires a written reason. **Failed** cannot be overridden. Approval locks adjustment controls until Unlock. Changing data, unconfirming units, or restoring a session revokes approval.
6. Export to a new file. Native exporters validate output before atomic replacement. A `.alignment.json` report records the matrix, source fingerprints, coordinate convention, QA and approval note.

Save projects as `.avsnap` JSON files. Restoring verifies source file paths, sizes and modification timestamps, reloads geometry, revalidates the transform and requires renewed review. These fingerprints detect ordinary source changes; they are not cryptographic content identities. Approved transformations are never trusted merely because a saved file says they were approved.

## Formats and preservation

| Format | Input | Export |
| --- | --- | --- |
| IFC | SI tessellation with area-dependent bounded sampling | Original model with root placements transformed once; all placed products and existing non-root entities checked after reopening |
| E57 | Every scan, poses, RGB and retained intensity; isolated process and disk-backed intermediate arrays | Original Cartesian scans, supported raw attributes and composed poses; validates all raw fields and world coordinates |
| LAS/LAZ | Chunked reading, RGB preview | Chunked native transformation preserving attributes, quantization scales and header metadata; reopened and checked |
| PLY/PCD/XYZ/PTS | Open3D-compatible point clouds | PLY/PCD/XYZ with XYZ roundtrip checks; PLY/PCD color checks |
| RCS/RCP/RVT | Clear Autodesk conversion guidance | No claimed native support |

Native IFC export preserves GUIDs, relationships, geometry, property entities and map-conversion metadata. Transforms operate in **local engineering coordinates**, not projected map coordinates. This distinction matters for georeferenced IFC models. Unsupported grid/linear placements are rejected. Models without placed products are rejected rather than silently exported unchanged.

Native E57 export rejects unsupported raw fields, spherical-only scans, embedded imagery and nonempty coordinate-reference metadata, because the current pye57 writer cannot preserve those safely. Convert through a suitable preserving workflow, or export a PLY derivative plus alignment report. E57 output is a new derivative with new scan GUIDs; arbitrary vendor metadata is not cloned. Native E57 is not a byte-for-byte archival copy.

LAS CRS mismatches between moving and anchor LAS files block export; reproject a copy first. LAS rotations containing waveform vectors are unsupported. XYZ is coordinates-only. Use binary PLY for large world coordinates when PCD's float precision fails validation. PLY/PCD exports do not claim to preserve arbitrary original E57/LAS attributes; use native exports for those.

## Efficiency and limits

- Full-cloud LRU cache, 512 MiB by default, keyed by path, file size and modification time; stale files are reloaded and callers receive independent copies.
- Shared multiresolution geometry inside each registration job; bounded solver point budgets of 15k/40k/80k.
- FGR first, with a 30,000-iteration bounded RANSAC fallback instead of the original 4 million iterations.
- Robust Tukey GICP at three scales, with scale-dependent correspondence rejection.
- Area-dependent IFC sampling capped at 250k points, rather than a fixed million.
- Preview capped at 100k points per dataset, independent of full-density native exports.
- Background registration/loading/export; cooperative cancellation between bounded native calls, and terminating isolated E57/manual workers on cancellation.

The interactive loader currently rejects more than **20 million points** before E57/LAS allocation. E57 processing holds one scan at a time and uses disk-backed extraction intermediates; the final Open3D cloud still occupies RAM. This is not a complete out-of-core, hundred-million-point engine. PLY/PCD are fully read by Open3D before their point count can be checked. Native export has no crash-recovery checkpointing. These are remaining engineering tasks, not completed features.

## Validation

```sh
python -m unittest discover -s tests -v
python benchmarks/registration.py --output benchmarks/results.json
# Optional identical-source comparison:
python benchmarks/registration.py --baseline /path/to/original-source --output benchmarks/results.json
python -m PyInstaller --noconfirm AV_Snap.spec
# Linux: dist/AV_Snap/AV_Snap --smoke-test
# Windows: dist/AV_Snap/AV_Snap.exe --smoke-test
```

The `tests/` suite generates its own IFC, E57, LAS and point-cloud fixtures. Legacy top-level scripts still reference excluded Windows customer datasets and are not the automated suite. See [implementation status](docs/MODERNIZATION.md) for exact checks and remaining work, and [benchmark results](benchmarks/results.json) for measured outcomes. Synthetic checks do not establish accuracy on production buildings.

Build on the target operating system. The executable bundles the existing official logo assets, displays a readiness-driven splash, and starts offline. Logs go to a writable per-user state directory (or a temporary fallback); override with `AV_SNAP_LOG_DIR`.

## AV Suite design

The Qt studio uses the actual AV Scan and AV scanAR palette: champagne `#BAA164`, luminous gold `#E5C983` and warm white `#FCFBF8`, with rounded glass cards and readable desktop opacity. Standard OS window controls, Qt keyboard navigation, high-DPI scaling and shortcuts are retained. There are no mandatory entrance animations or artificial splash delays.

Reference implementations: [AV Scan](https://github.com/callen0817/av-scan/blob/main/gui/qml/AppWindow.qml) and [AV scanAR](https://github.com/callen0817/av-scanar/blob/main/src/scanhub_gui/scanhub_app.py). They are design references, not runtime dependencies.

## Ownership

Copyright (c) 2026. All rights reserved. Third-party components retain their respective licences.
