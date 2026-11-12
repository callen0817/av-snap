# Changelog

## Unreleased — alignment correctness and AV Suite studio

- Replace per-product IFC placement collapse with one transform per placement root, all-product world-space validation, unchanged original entities, unit conversion, source protection and atomic save.
- Reject simulated RVT/RCS/RCP input; ingest every E57 scan with pose and supported attributes. Preserve scan structure during native E57 export, with explicit unsupported metadata errors.
- Add chunked LAS/LAZ I/O and attribute-preserving, validated native export.
- Compare bounded alignment candidates; use robust multiresolution GICP, optional upright prior, bidirectional QA and ambiguity flags.
- Add caching, worker cancellation, correct completion-signal ordering, project persistence, control points, adjustments, undo/redo, approval locks and structured alignment reports.
- Introduce the glass-and-gold AV Suite studio, GPU preview, sections, error colors, camera controls and a logo splash tied to actual readiness.
- Remove launch-time package installation; declare Open3D and desktop dependencies, repair PyInstaller configuration and add regression CI.
- Add generated-data regression tests and reproducible before/after synthetic benchmarks. See docs/MODERNIZATION.md for limits and unverified workflows.
