# Excluded data and local rebuild

Point clouds, BIM models, Python virtual environments, build/dist folders, runtime logs, bytecode and editor caches are excluded by `.gitignore`. Existing customer E57 and IFC models referenced by top-level diagnostic scripts are not included and are not reconstructed by the application.

For supported installation, generated regression fixtures and packaging commands, use [README.md](README.md). The reproducible suite is `python -m unittest discover -s tests -v`, not the legacy top-level scripts that reference Windows downloads.

Logo variants in `logos/` and the existing marketing video in `ads/` remain tracked. The new splash uses the existing official `logos/av_snap.png` without altering the asset. PyInstaller bundles `logos/`; it does not include the marketing video, customer files or internal conversation history. There are no artificial splash playback delays.

`docs/antigravity-history/` remains in source history and warrants the public-content review described in [docs/MODERNIZATION.md](docs/MODERNIZATION.md). This is not a runtime dependency.
