# Electrophoresis Labeller — Project Plan

## Context

The goal is a cross-platform **desktop application** that lets non-technical
lab scientists go from a raw gel electrophoresis image to quantified,
molecular-weight-calibrated, annotated results — fully offline, with
double-click installers and no Python/terminal setup.

Today the repository is greenfield (only `README.md`, `LICENSE`,
`.gitignore`). The central architectural driver is **decoupling the
image-processing engine from the GUI from day one**, so the same engine can
later back a FastAPI web version without modification. Every structural
decision below serves that goal plus the "robust enough for messy real gels,
but manual correction always available" product reality.

This document is the agreed plan and the source of truth for implementation.

### Decisions locked with the user

| Decision | Choice |
|---|---|
| Project ↔ Image | **Multi-image project** (one Project → many Images) |
| Lane geometry in v1 | **Straight vertical lanes + manual correction**; smiling/skew deferred to M4 |
| MW calibration | **Log-linear default + optional cubic-spline**, report r² |
| Python floor | **`requires-python >= 3.11`** (explicit override of the original "3.12+"; lets code run/build directly in this container, no extra interpreter). Avoid 3.12-only syntax. |

### Defaults adopted without further questions (overridable later)

- Pixel data referenced by **relative path + sha256**, never embedded in JSON.
- Session = **sidecar JSON** next to the image, with project-relative path refs.
- Export = **CSV + XLSX data table + annotated PNG** (annotated TIFF optional, later).
- 16-bit TIFF: **full precision retained for quantification**; canvas shows an
  auto-contrast 8-bit tone-mapped view only.
- Cross-lane / loading-control normalization: **out of scope for v1**.
- macOS notarization / Windows code-signing: **flagged as an open M5 input**, not decided now.

---

## 1. Package / directory layout

**Decision: `src` layout, monorepo with two independently installable
packages** (`gel_core`, `gel_app`) wired via path/workspace dependency.

```
electrophoresis_labeller/
  PLAN.md                       # this document (committed first)
  pyproject.toml                # root: workspace + shared dev tooling (ruff, mypy, pytest)
  packages/
    gel_core/
      pyproject.toml            # deps: numpy scipy opencv-python-headless scikit-image tifffile imageio
      src/gel_core/
        __init__.py
        models.py               # dataclasses for the data model
        io_ports.py             # Protocols: ImageReader, ProjectStore (dependency inversion)
        imageio_backend.py      # default local ImageReader -> ndarray
        serialization.py        # model <-> dict <-> JSON; schema_version handling
        params.py               # frozen dataclasses of named CV params (defaults only)
        errors.py               # GelCoreError hierarchy (no GUI coupling)
        pipeline/
          __init__.py           # run_pipeline orchestrator
          preprocess.py
          lanes.py
          bands.py
          quantify.py
          calibrate.py
    gel_app/
      pyproject.toml            # deps: pyside6, gel_core (path/workspace dep)
      src/gel_app/
        __init__.py
        main.py                 # QApplication bootstrap / Briefcase entry point
        main_window.py
        canvas/                 # QGraphicsView/Scene + lane/band/label items
        docks/                  # lane/band tree, data table, calibration, params, log
        controllers/            # mediate models <-> widgets; own worker threads
        workers.py              # QThreadPool/QThread wrappers calling gel_core
        adapters.py             # Qt impls of gel_core io_ports Protocols
        resources/              # icons + one bundled sample gel
  tests/
    core/                       # pure pytest, no Qt
    app/                        # pytest-qt headless
    data/                       # sample TIFF/PNG + golden outputs
```

**Why these boundaries:**

- **`gel_core` has zero Qt imports**, enforced three ways: (a) its
  `pyproject.toml` never depends on PySide6; (b) a CI guard test that
  AST/grep-scans `gel_core/` and fails on any `PySide6`/`PyQt` token;
  (c) `mypy` run on `gel_core` in isolation.
- **No I/O policy in core.** Core takes an already-decoded `np.ndarray` plus a
  `Protocol` (`io_ports.ImageReader`) for byte fetching. Desktop injects a
  local-filesystem reader; a future FastAPI server injects an HTTP/object-store
  reader — `gel_core` unchanged. Core never calls `QFileDialog` or assumes
  filesystem semantics beyond an opaque URI string.
- **Core returns numpy / stdlib dataclasses only** — never `QImage`/`QPolygonF`.
  The GUI adapts geometry to Qt graphics items in `gel_app`.
- **Pipeline functions are pure** (new output, no input mutation, no global
  state) → deterministic golden-file tests and trivial web-worker reuse.
- **Monorepo, not two repos:** v1 churns the data model heavily; one repo keeps
  the loop fast. Split into separate repos only if/when the web version lands.
- **`src` layout:** prevents "tests import the uninstalled tree" foot-guns and
  packages cleanly under Briefcase.

---

## 2. Core data model

**Use stdlib `@dataclass` (frozen where practical), not pydantic.** `gel_core`
must stay dependency-light for embedding/server reuse; serialization is a small
explicit JSON mapping we own; validation lives at the `from_dict` boundary and
in the GUI input layer.

**Relationships:** Project 1→N Image; Image 1→N Lane; Lane 1→N Band. A
**Ladder** is a Lane with `role = LADDER` plus a sidecar `Ladder` record
(ordered known MW values + band assignments) referencing that lane's id —
keeps `Lane` uniform, no subclassing. **Calibration** belongs to an Image,
derived from its ladder lane (one active per Image). **Annotation** is
user-authored overlay keyed by id to Image/Lane/Band, kept separate from
detected geometry so re-running detection never destroys manual labels.

**Key fields** (`*` = derived, recomputed on load, not serialized):

- `Project(id, name, schema_version, created_at, images, params_overrides)`
- `Image(id, source_uri[project-rel], checksum_sha256, width, height, bit_depth, lanes, calibration, annotations, preprocess_params)`
- `Lane(id, index, role[SAMPLE|LADDER], x_bounds, bands, manual_edited)`
- `Band(id, lane_id, y_center, y_bounds, raw_intensity*, net_intensity*, mw*, label, confidence, source[AUTO|MANUAL])`
- `Ladder(lane_id, known_mw: list[float], assigned_band_ids: list[id|None])`
- `Calibration(image_id, model[LOG_LINEAR|SPLINE], coefficients, r_squared*, fit_points)`
- `Annotation(id, target_id, kind, geometry, text, color)`

**Serialized to JSON:** ids, names, `schema_version` (mandatory from day one
for migrations), image `source_uri`+`checksum_sha256`+`bit_depth`, lane
bounds/roles, band y-bounds/labels/source, ladder `known_mw`+assignments,
calibration model+coefficients+fit_points, annotations, param overrides.

**Derived / in-memory only:** decoded pixel arrays, lane intensity profiles,
background-subtracted intensities, `r_squared`, rendered overlays, QGraphics
items.

**Pixel data:** referenced by project-relative path + sha256, never embedded.
On load: verify checksum, **warn (don't hard-fail)** on mismatch.

---

## 3. CV pipeline (pure functions in `gel_core`)

Signature pattern: `(ndarray | dataclass, Params) -> dataclass | ndarray`,
deterministic, no input mutation. **v1 assumes straight, vertical lanes,
migration top→bottom** (smiling correction = M4).

1. **`load(uri, reader) -> RawImage`** — tifffile/imageio decode, preserve
   native dtype (uint8/uint16). *Fails on:* unsupported codec; multi-page TIFF
   (take page 0 + warn); bit-depth ambiguity.
2. **`preprocess(RawImage, PreprocessParams) -> PreImage`** — grayscale; auto
   polarity invert (mean heuristic); normalize to float[0,1] (store scale for
   intensity back-conversion); rolling-ball / morphological top-hat background
   estimate; mild Gaussian denoise. Params: `invert`, `rolling_ball_radius`,
   `gaussian_sigma`, `normalize_percentiles`. *Fails on:* wrong polarity;
   over-aggressive background erasing faint bands.
3. **`detect_lanes(PreImage, LaneParams) -> list[Lane]`** — vertical-mean
   collapse → 1-D x-profile → smooth → `scipy.signal.find_peaks` for
   centers/boundaries; enforce min width/spacing. Params:
   `expected_lane_count?`, `min_lane_width`, `min_lane_spacing`,
   `smoothing_sigma`, `prominence`. *Fails on:* merged lanes, skew, uneven
   loading, edge artifacts → manual correction in GUI.
4. **`detect_bands(PreImage, Lane, BandParams) -> list[Band]`** — per-lane
   column ROI → 1-D y-profile → baseline-correct → `find_peaks` +
   `peak_widths`. Params: `min_band_prominence`, `min_band_distance`,
   `max_bands`, `peak_width_rel_height`. *Fails on:* smearing, overlap,
   saturation plateaus, faint sub-prominence bands.
5. **`quantify(PreImage, Band, QuantParams) -> BandQuant`** — integrate
   intensity over the band y-window in the lane ROI; background subtraction
   (rolling-ball + per-band local baseline = median of flanking windows) →
   `net_intensity`; report raw/net/area/peak; convert back via stored
   normalization scale for 16-bit fidelity. Params: `baseline_method`,
   `flank_window_px`, `integration_window`. *Fails on:* overlapping bands
   sharing signal; negative net from over-subtraction (clamp + warn).
6. **`calibrate_mw(Ladder, bands, CalibParams) -> Calibration`** +
   **`apply_calibration(Calibration, Band) -> mw`** — default **log-linear**
   `log10(MW) = a·Rf + b` via least squares; **optional cubic spline**;
   report r². Params: `model`, `min_points(>=3)`, `use_rf`. *Fails on:*
   too few / non-monotonic ladder points; mis-detected ladder; extrapolation
   beyond ladder range (flag predicted MWs as extrapolated).

`run_pipeline` chains these; each stays independently callable and golden-tested.

---

## 4. GUI structure (`gel_app`)

- **MainWindow:** menu/toolbar (Open, Save/Load Session, Run Detection,
  Export), central `CanvasView`, dock widgets.
- **Docks:** lane/band tree; pandas-backed band data table
  (`QAbstractTableModel`); calibration panel (assign ladder MWs, r² + fit
  plot); parameters panel (live CV params + re-run); log/status.
- **CanvasView:** `QGraphicsView` + `QGraphicsScene`.
  - `GelImageItem` (16-bit tone-mapped to 8-bit for display; original retained
    in core).
  - `LaneItem` (resizable rect), `BandItem` (movable/resizable),
    `LabelItem` — each carries its model id; edits emit signals → controller
    updates model → marks `manual_edited`.
  - Zoom (Ctrl+wheel, anchor under cursor), pan (space/middle-drag),
    fit-to-window; item LOD + tiled pixmap for very large TIFFs.
- **Controllers** own the project model and mediate; no business logic in
  widgets. GUI implements `gel_core`'s `ImageReader`/`ProjectStore` Protocols
  in `adapters.py`.
- **Threading:** every `gel_core` pipeline call runs in a
  `QThreadPool`/`QThread` worker; UI shows progress, stays responsive; results
  delivered via queued signals. **Never run OpenCV/SciPy on the UI thread.**

**End-to-end click-path:** Open Image → worker auto-runs preprocess + lane +
band detection (progress bar) → review on canvas, drag/add/delete lanes &
bands → mark a lane as Ladder, enter & assign known MWs → Calibrate (see r²)
→ band table fills with MW + net intensity → edit labels → Export (annotated
PNG + CSV/XLSX) → Save Session (JSON sidecar).

---

## 5. Milestones

- **M1 — Walking skeleton (true end-to-end).** One bundled sample image flows
  through *every* stage with crude algorithms (grayscale/normalize → threshold
  lane split → simple peak bands → raw integration → log-linear calibration
  with hardcoded ladder). Minimal GUI: open, see image + boxes, run, export
  CSV + annotated PNG, save/load JSON. Both packages wired; CI
  (ruff/mypy/pytest) green; "no Qt in core" guard test passing.
  **Deliverable: a clickable app producing a real (rough) result + a golden
  test.** Includes the **packaging spike** (risk #1) early, not at M5.
- **M2 — Real detection.** Profile+peak lane detection, prominence-based band
  detection with named params; params dock; manual add/move/delete on canvas;
  correct 16-bit TIFF handling. Golden tests over a small image set.
- **M3 — Quantification & calibration UX.** Rolling-ball + local-baseline
  background subtraction; ladder-assignment UI; r² + fit plot; MW propagation;
  sortable/editable band table; XLSX export; polished threading + progress.
- **M4 — Robustness.** Smiling/skew handling (per-lane vertical re-alignment
  or lane-axis warp); saturation/faint-band handling; undo/redo; session
  schema migration; checksum-mismatch recovery; multi-image project UX.
- **M5 — Packaging & polish.** Briefcase double-click installers for
  Win/macOS/Linux (offline, native wheels bundled); code-signing/notarization
  decision + execution; onboarding/help; large-TIFF perf tuning; validated
  PyInstaller fallback.

---

## 6. Top 3 risks + de-risking spikes

1. **Briefcase packaging of OpenCV/SciPy native wheels, offline, 3 OSes.**
   *Spike (in M1):* minimal Briefcase app importing cv2+scipy+skimage+PySide6;
   build installers on all 3 OSes fully offline; launch on clean VMs. Decide
   `opencv-python-headless` (core) vs full (app); keep a PyInstaller fallback
   recipe ready. Front-loaded because it can force dependency changes.
2. **Lane/band detection robustness on noisy/smiling real gels.** *Spike:* run
   the profile+peak prototype on ~5 varied real gels (clean, smiling, faint,
   overloaded); measure hit/miss; confirm v1 ships "manual-correction-first"
   and that smiling stays M4.
3. **QGraphicsView performance with large 16-bit TIFFs + many items.** *Spike:*
   load a 50–200 MP TIFF, render hundreds of band items, profile pan/zoom FPS;
   evaluate downsampled display pixmap + tiling + item LOD; set a perf budget
   before building the full canvas.

---

## 7. Verification (how we prove it works end-to-end)

- **Core unit + golden tests:** `pytest tests/core` — each pipeline function
  has a deterministic golden-file test on the bundled sample image
  (`tests/data/`); `run_pipeline` has an end-to-end golden test asserting a
  stable band table + calibration coefficients.
- **Architecture guard:** a test that scans `packages/gel_core/` and fails on
  any `PySide6`/`PyQt` import; `mypy packages/gel_core/src` passes in isolation.
- **GUI smoke tests:** `pytest tests/app` under `pytest-qt` headless
  (`QT_QPA_PLATFORM=offscreen`) — open sample image, run detection worker,
  assert items appear, trigger export, assert output files exist.
- **Manual M1 acceptance:** launch the app, open the bundled sample, click Run,
  see lane/band boxes, Calibrate, Export → verify the CSV/PNG/JSON on disk and
  reload the session.
- **Lint/format/type gate:** `ruff check`, `ruff format --check`, `mypy` all
  green in CI (GitHub Actions, Python 3.11).
- **Packaging acceptance (M1 spike + M5):** `briefcase build`/`run` produces a
  launchable artifact on each OS; smoke-launch on a clean machine offline.

---

## 8. Critical files to create (execution order)

1. `PLAN.md` (this document, committed first)
2. `pyproject.toml` (root workspace + tooling)
3. `packages/gel_core/pyproject.toml`
4. `packages/gel_core/src/gel_core/models.py`
5. `packages/gel_core/src/gel_core/io_ports.py`
6. `packages/gel_core/src/gel_core/serialization.py`
7. `packages/gel_core/src/gel_core/pipeline/__init__.py` (+ stage modules)
8. `packages/gel_app/pyproject.toml`
9. `packages/gel_app/src/gel_app/main.py` + `main_window.py`
10. `tests/` (core golden tests, app smoke tests, sample data)
11. `.github/workflows/ci.yml` (ruff/mypy/pytest, Python 3.11)

Branch: all work on `claude/plan-gel-analysis-tool-vyoio`.
