# Modernization implementation status

## Scope and sequence

The requested suite order is AV Snap → AV Segment → AV Splat. The other remotes initially contained only scaffolds. After the user confirmed that no implementation existed, new independently runnable Segment and Splat applications were built and tested. Their own modernization reports distinguish geometry/CPU conversion from trained-model, CUDA and production acceptance work. AV Splat now includes both Point → Splat and Splat → Point, with explicit derived-point provenance. Matching black-and-gold Snap and Segment artwork is loaded from existing repo assets; exact downloadable Splat artwork remains pending.

The AV Snap changes implement the correctness and desktop foundations described in the request. They do not establish production readiness for every item in the wider modernization specification.

## Implemented

- Dedicated rigid-transform and IFC export modules. Nested/multiple/shared roots are transformed once in native units. Every placed product is checked in world coordinates; all original non-root entities are compared on reopening, preserving geometry, GUIDs, relationships and metadata. Existing output survives validation failure. The source cannot be overwritten, including through a hard link.
- No synthetic placeholder geometry for unsupported Autodesk formats. Explicit conversion requirements replace fake success.
- All-scan E57 loading with individual poses, RGB and intensity, unique temporary directories and subprocess isolation. Native Cartesian E57 export composes each scan pose and validates original raw fields, color/intensity and transformed coordinates. Unsupported CRS/image/vendor fields are explicitly limited, not silently advertised as preserved.
- LAS/LAZ chunked I/O, original-attribute preservation and validation. Differing known LAS CRSs are rejected for native export; waveform rotation is rejected.
- Coordinate/yaw/FPFH candidates, FGR plus bounded RANSAC fallback, multiresolution Tukey GICP, optional upright constraint and independent geometric QA. Matching transform initializations are distinguished from genuinely different competing solutions.
- Manual correspondences with degeneracy checks and refinement, entered control coordinates, adjustments, undo/redo/reset, candidate comparison, saved sessions, renewed restore QA and approval locks. Worker results are complete before the completion signal.
- Native file writers and reports run in background jobs. E57/manual subprocesses can be cancelled; other native calls finish their bounded stage before cancellation takes effect.
- The requested AV Scan/scanAR design tokens, readable Qt glass cards, high-DPI support, keyboard shortcuts, OS window controls, official existing logos and readiness-based splash. GPU point preview, independent visibility/opacity, original/aligned modes, error colors, camera presets and axis sections are wired to real data. Coordinate measurement is available through an explicit two-point dialog.
- Explicit dependencies, offline startup, target-OS PyInstaller configuration and Linux/Windows CI definitions. No mandatory Autodesk runtime or cloud AI service.

## Quality criteria

`Validated` is a conservative geometric gate, **not** a calibrated confidence probability or a survey accuracy certificate. The current gate uses:

- Directed source/target overlap within 2.5 times the solver voxel size.
- Failure below 15% overlap in either direction.
- Review below 65% source overlap, below 35% target overlap, or P95 inlier residual above 90% of the distance gate.
- Review for near-planar/linear covariance or distinct transforms within 0.03 of the best overlap score.
- Candidate ambiguity when alternatives differ by more than 5° or three solver voxels.

These thresholds need calibration on representative buildings. Residual statistics cover inliers; overlap accounts for excluded residuals. The validator does not estimate probabilistic uncertainty or prove that repeating rooms/floors were matched correctly. Sampled visual error colors are separate from the QA measurements.

## Validation evidence

The generated-data suite runs with `python -m unittest discover -s tests -v`. It covers rigid math, known transformations, ambiguity, low overlap, manual degeneracy, cancellation, threaded GUI responsiveness, approval state, session restore, source changes, IFC hierarchy/units/map-conversion metadata/tessellation, atomic rollback, E57 multiscan rotations and attributes, LAS attributes, and cache invalidation.

Linux source startup and the Linux frozen executable were exercised. The OpenGL viewer was also exercised under Xvfb/Mesa with overlays, error colors, camera changes and section controls; screenshots were inspected. This checks software rendering, not physical GPU performance. Mouse-driven Open3D correspondence picking still needs a final operator validation on the intended desktop.

Windows builds and tests are configured in CI but have not run in this cloud machine. Real customer E57/IFC datasets referenced by the legacy scripts are excluded. No claim is made that those tests ran, that ReCap/Revit interoperability was validated, or that packaged Windows deployment has passed.

`benchmarks/results.json` records identical-seed synthetic measurements against original commit `fa7907f158b85bb2d585eb13dcafdd296947f66f`, using 3,000 points and two CPU threads. In this run, sampled process memory fell from roughly 449–450 MiB to 237–238 MiB. Translation-only processing took about 2.12 seconds versus 1.35 seconds; tilted registration took about 1.77 seconds versus 1.89 seconds. Additional candidate checking has a cost. The tilted-cloud translation/rotation error was lower in the new implementation, but this small artificial example does not establish real-building accuracy or a general runtime improvement. Open3D global matching has stochastic components; timings and results can vary.

## Remaining work and external validation

- Full out-of-core ingestion/registration beyond the explicit 20-million-point interactive budget; per-scan E57 native writers still allocate scan arrays.
- Disk-backed shared caches across applications, streaming PLY/PCD, change-only processing, durable resumable jobs, process-wide peak RAM/VRAM telemetry and GPU acceleration benchmarks.
- Architecture-aware plane/control feature extraction, uncertainty calibration and production-dataset acceptance criteria.
- Per-element IFC hierarchy/filtering in the viewer, object-level review, interactive marker editing and snap-to-plane assistance.
- Persistent annotation/selection history and a dedicated point-picking measurement tool; current measurement takes coordinates.
- Faithful native E57 export of spherical scans, embedded imagery and coordinate/vendor metadata; these paths are rejected today.
- Operator acceptance on the supported Windows desktop, actual manual point picking, large customer projects, ReCap roundtrips and release packaging/signing.
- AV Segment and AV Splat implementation after their existing source and official assets are accessible, in that order.

## Public-content review

`docs/antigravity-history/` contains internal AI conversation records, local paths and project/customer dataset references. A focused pattern scan found no matching common private-key, GitHub-token, AWS-access-key or long OpenAI-key signatures; this is not a comprehensive secret audit. The records were not copied into the new desktop package. Existing files and Git history were preserved. Review and sanitize the original history before any new public release; a historical removal/rotation decision is separate from changing the current application.
