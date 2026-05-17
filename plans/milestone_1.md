# Milestone 1 — Walking Skeleton: Delegatable Subtask Briefs

> Source of truth: `PLAN.md` (committed at repo root). This file decomposes the
> M1 milestone (`PLAN.md` §5) into 8 self-contained subtasks. Each subtask is
> delegated to a separate fresh agent.

---

## Part A — How to use this file

- Each subtask below is delegated to **one agent**. That agent must read
  `PLAN.md` first (the specific sections are cited in each brief) and treat it
  as binding.
- Respect the dependency map in **Part C**. Do not start a subtask before its
  hard dependencies are merged.
- **Subtask 2 is a contract freeze.** A human must eyeball its public API
  (dataclass fields, Protocol signatures) before Wave 2 fans out — a later
  rename is a multi-subtask break.
- Toolchain: a single `uv` workspace at repo root. Standard commands:
  `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`,
  `uv run mypy …`.
- `requires-python >= 3.11`. The interpreter present is 3.12.12 — code must run
  on it but must **avoid 3.12-only syntax**.
- Branch: continue on the current working branch (do not create new branches
  per subtask unless the delegator instructs otherwise).
- Each brief states what is **Out of scope** — do not pull M2/M3 sophistication
  forward. "Crude but real" is explicitly licensed by `PLAN.md` §5 M1.

### Confirmed product decisions (binding for all subtasks)

| Topic | Decision |
|---|---|
| Sample image | **Synthetic, seeded script.** A real gel asset is deferred to a later milestone. |
| M1 canvas boxes | **Movable + deletable** (minimal drag/delete). Add/resize stays M2. |
| Packaging spike | **Unsigned launchable macOS bundle.** No notarization in M1 (stays M5). Win/Linux deferred to M5 but documented. |
| Export split | **CSV in `gel_core`** (pure). **Annotated PNG in `gel_app`** (Qt render). |
| `load()` placement | Lives in `imageio_backend.py`, re-exported by `pipeline/__init__.py`. **Subtask 3 owns it.** |
| Pipeline ndarray types | `RawImage`/`PreImage`/`BandQuant` live in `pipeline/_types.py`, **owned by Subtask 4**. Never serialized; not in `models.py`. |
| CI Python | **3.11 only** for M1. Version matrix is an M5 concern. |

---

## Part B — Subtask briefs

Each brief: **Objective**, **Owns/creates**, **Hard dependencies**,
**Key spec**, **Acceptance criteria**, **Out of scope**.

---

### Subtask 1 — Repo scaffold, `uv` workspace, dependency declarations, canonical synthetic sample image

**Objective.** Stand up the monorepo skeleton so every later agent has a
syncable, importable workspace and one deterministic sample image to consume.
No application logic.

**Owns / creates.**
- Root `pyproject.toml`: `uv` workspace with members `packages/gel_core` and
  `packages/gel_app`; shared dev deps `ruff`, `mypy`, `pytest`, `pytest-qt`;
  `[tool.ruff]`/`[tool.mypy]`/`[tool.pytest.ini_options]` config;
  `requires-python = ">=3.11"`.
- `packages/gel_core/pyproject.toml`: deps `numpy scipy opencv-python-headless
  scikit-image tifffile imageio`; build backend + package metadata.
  **Must NOT list `pyside6`/`pyqt`.**
- `packages/gel_app/pyproject.toml`: deps `pyside6` + `gel_core` as a workspace
  dependency. Leave a **placeholder comment** for the Briefcase config
  (`[tool.briefcase]` is owned by Subtask 8 — do not author it here).
- All `__init__.py` for both packages and the `pipeline/` subpackage (empty but
  present so imports resolve).
- `tests/__init__.py`, `tests/conftest.py` (with a `sample_image_path` fixture
  pointing at the canonical path), `tests/core/__init__.py`,
  `tests/app/__init__.py`.
- **Canonical sample image**: `tests/data/make_sample.py` (deterministic, fixed
  RNG seed) + byte-identical `tests/data/sample_gel.tif` **and**
  `packages/gel_app/src/gel_app/resources/sample_gel.tif`.

**Hard dependencies.** None. This is Wave 0 — the total gate.

**Key spec.**
- Synthetic gel: 16-bit grayscale, ~6 vertical lanes; one designated **LADDER**
  lane with ~5 well-separated bands at known y-centers; sample lanes with 2–4
  bands. Document polarity (dark-on-light or inverted) in the module docstring.
- Expose geometry as **module constants** in `make_sample.py`: lane x-centers,
  ladder band y-centers, ladder known-MW list. Subtasks 2 and 4 import or mirror
  these — they are the single source for golden tolerances and the hardcoded
  ladder.
- Workspace layout must match `PLAN.md` §1 exactly.

**Acceptance criteria.**
- `uv sync` from repo root installs the full numpy/scipy/skimage + pyside6 stack
  plus dev tooling without error on Python 3.11+ (runs on the 3.12.12
  interpreter present).
- `uv run python -c "import gel_core, gel_app"` succeeds (empty packages import
  cleanly).
- `uv run python tests/data/make_sample.py` is idempotent: regenerates
  byte-identical `.tif` at both paths; prints a checksum that is stable across
  two runs.
- `uv run pytest` collects 0 tests and exits 0 (no collection errors).
- `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` are runnable
  from root (pass trivially on the empty tree).
- `git status` confirms the sample `.tif` is tracked (not matched by
  `.gitignore`; only `build/`, `dist/`, `*.spec` are ignored — harmless here).

**Out of scope.** Any app or CV logic. A real gel image. Briefcase config.

---

### Subtask 2 — Core contract: models / io_ports / params / errors / serialization (FREEZE)

**Objective.** Define every dataclass, Protocol, params type, error type, and
the JSON round-trip. This is the frozen contract every other subtask codes
against. No Qt, no numpy-heavy logic, no I/O.

**Owns / creates.**
- `packages/gel_core/src/gel_core/models.py`
- `packages/gel_core/src/gel_core/io_ports.py`
- `packages/gel_core/src/gel_core/params.py`
- `packages/gel_core/src/gel_core/errors.py`
- `packages/gel_core/src/gel_core/serialization.py`
- `tests/core/test_serialization.py`

**Hard dependencies.** Subtask 1. **HARD GATE — human reviews this API before
Wave 2 starts.**

**Key spec.**
- `models.py`: stdlib `@dataclass` (frozen where practical), **fields exactly
  per `PLAN.md` §2** — `Project, Image, Lane, Band, Ladder, Calibration,
  Annotation`. Enums for `Lane.role` (SAMPLE|LADDER), `Band.source`
  (AUTO|MANUAL), `Calibration.model` (LOG_LINEAR|SPLINE). `schema_version`
  mandatory on `Project`. Derived fields (`raw_intensity`, `net_intensity`,
  `mw`, `r_squared`) are NOT serialized and recomputed on load.
- `io_ports.py`: `typing.Protocol` definitions `ImageReader` (opaque URI →
  bytes/ndarray) and `ProjectStore` (load/save dict). No filesystem assumptions
  in the Protocol itself.
- `params.py`: frozen dataclasses with M1 defaults only — `PreprocessParams,
  LaneParams, BandParams, QuantParams, CalibParams` plus a top-level
  `PipelineParams` aggregate. Field names per `PLAN.md` §3.
- `errors.py`: `GelCoreError` base + subclasses (`ImageLoadError`,
  `CalibrationError`, …). No GUI coupling.
- `serialization.py` per `PLAN.md` §2: `to_dict`/`from_dict`/`dumps`/`loads`;
  `schema_version` written and checked; pixel data never embedded (only
  `source_uri` + `checksum_sha256`); checksum mismatch **warns, does not raise**;
  unknown/missing `schema_version` raises a typed `GelCoreError`.

**Acceptance criteria.**
- `uv run mypy packages/gel_core/src` passes in isolation (no `Any` leakage on
  the public model surface).
- Round-trip test: in-memory `Project` → `dumps` → `loads` → structural
  equality for serialized fields; derived fields are absent from the JSON;
  `schema_version` present.
- `from_dict` on mismatched/missing checksum **warns and continues** (explicitly
  tested, not raising).
- `from_dict` on unknown/missing `schema_version` raises a typed error.
- All seven dataclasses instantiate with the `PLAN.md` §2 field set verbatim.
- No `PySide6`/`PyQt`/`numpy` import in any of these five modules.

**Out of scope.** Pipeline-internal ndarray types (Subtask 4). Any actual I/O
or decoding.

---

### Subtask 3 — Default local image I/O backend + `load()`

**Objective.** Implement `load()` and the default filesystem `ImageReader`
that decodes the sample TIFF to an ndarray preserving native dtype.

**Owns / creates.**
- `packages/gel_core/src/gel_core/imageio_backend.py` — concrete `ImageReader`
  implementing the Subtask 2 Protocol; `load()` defined here and re-exported by
  `pipeline/__init__.py` (the re-export line is added by Subtask 4 — coordinate
  via the import path, do not edit `pipeline/__init__.py` here if it does not
  yet exist; expose `load` at module level so Subtask 4 can re-export it).
- `tests/core/test_io.py`

**Hard dependencies.** Subtask 1 (sample image + workspace), Subtask 2
(`ImageReader` Protocol + `errors`).

**Key spec.** Per `PLAN.md` §3 step 1: tifffile/imageio decode preserving native
dtype (uint8/uint16); multi-page TIFF → take page 0 + warn; unsupported codec →
typed `ImageLoadError`; bit-depth ambiguity handled explicitly.

**Acceptance criteria.**
- Loading `tests/data/sample_gel.tif` returns an ndarray with dtype and shape
  exactly matching the `make_sample.py` constants.
- 16-bit input retains uint16 (no silent 8-bit truncation).
- Unsupported path raises `ImageLoadError` (typed, no Qt).
- `uv run mypy packages/gel_core/src` clean in isolation; zero Qt tokens.

**Out of scope.** Preprocessing, lane/band logic (Subtask 4).

---

### Subtask 4 — CV pipeline: 6 stages + `run_pipeline` + CSV export + golden tests

**Objective.** Implement crude-but-real versions of all six pipeline stages,
the chaining orchestrator, and the pure CSV export, with deterministic golden
tests on the canonical sample image. Largest single subtask; on the critical
path.

**Owns / creates.**
- `packages/gel_core/src/gel_core/pipeline/_types.py` — non-serialized ndarray
  carriers `RawImage`, `PreImage`, `BandQuant`.
- `packages/gel_core/src/gel_core/pipeline/preprocess.py`
- `packages/gel_core/src/gel_core/pipeline/lanes.py`
- `packages/gel_core/src/gel_core/pipeline/bands.py`
- `packages/gel_core/src/gel_core/pipeline/quantify.py`
- `packages/gel_core/src/gel_core/pipeline/calibrate.py`
- `packages/gel_core/src/gel_core/pipeline/__init__.py` — `run_pipeline`
  orchestrator; re-exports `load` from `imageio_backend`.
- A pure CSV band-table export function in `gel_core` (per the confirmed export
  split — CSV is core, PNG is app).
- `tests/core/test_pipeline_stages.py`, `tests/core/test_run_pipeline_e2e.py`.

**Hard dependencies.** Subtask 2 (models/params/errors — frozen), Subtask 3
(`load`/`ImageReader`). Effectively starts after both.

**Key spec.** Crude algorithms only, per `PLAN.md` §5 M1 and §3:
- preprocess: grayscale, polarity auto-invert (mean heuristic), normalize
  float[0,1] storing scale, crude background (simple morphological top-hat or
  constant — crude is fine), mild Gaussian.
- lanes: vertical-mean collapse → x-profile → smooth → `find_peaks` (or simple
  threshold split) → `Lane` list with `x_bounds`.
- bands: per-lane y-profile → `find_peaks` → `Band` list with `y_bounds`.
- quantify: raw integration over the band window → `raw_intensity`/
  `net_intensity` (no rolling-ball/local-baseline — that is M3).
- calibrate: log-linear least squares `log10(MW)=a·Rf+b`, report r²;
  `apply_calibration` → mw per band; **hardcoded ladder** = the known-MW
  constants from `make_sample.py`.
- `run_pipeline(uri, reader, params)` chains load→preprocess→detect_lanes→
  detect_bands→quantify→calibrate. Pure; no input mutation; no global state.

**Acceptance criteria.**
- Each stage is a pure function: same input → same output; input ndarray/
  dataclass not mutated (assert input array unchanged after the call).
- Golden tests deterministic across two consecutive runs (no RNG, no
  thread-order dependence).
- `run_pipeline` on the sample → ≥1 ladder lane; ladder bands within a
  documented pixel tolerance of the known y-centers; log-linear r² above a
  documented threshold (>0.99 on clean synthetic).
- CSV export writes a band table to disk.
- Tolerances are named constants in the test module with a comment explaining
  why (so M2 can tighten them).
- `uv run mypy packages/gel_core/src` clean in isolation; zero Qt tokens.

**Out of scope.** Rolling-ball / local-baseline subtraction (M3),
prominence-tuned detection (M2), cubic spline, annotated-PNG rendering
(Subtask 6).

---

### Subtask 5 — Architecture guard test ("no Qt in core")

**Objective.** The CI guard that scans `packages/gel_core/` and fails on any
Qt import, plus asserting the core pyproject lists no Qt dependency.

**Owns / creates.** `tests/core/test_architecture_guard.py`.

**Hard dependencies.** Subtask 1 (package layout exists). Author against the
tree; it lands green in Wave 2 and must stay green as later core code merges.

**Key spec.** Per `PLAN.md` §7 Architecture guard: walk every `.py` under
`packages/gel_core/src/`, AST-parse (token-scan fallback) for any `PySide6`,
`PyQt5`, `PyQt6`, or `qt` import; fail with the offending file/line. Also assert
`packages/gel_core/pyproject.toml` declares no Qt dependency. Ignore
`__pycache__`.

**Acceptance criteria.**
- Passes against the current (Qt-free) core.
- Demonstrably fails when an `import PySide6` line is temporarily injected into
  any core module (show this via a scratch experiment — **do not commit it**).
- Scans recursively, not just top-level.

**Out of scope.** Wiring into CI (Subtask 8 does that).

---

### Subtask 6 — Minimal GUI: window, canvas (drag/delete boxes), Run/Export/Save/Load, Qt adapters

**Objective.** A clickable PySide6 app: open the sample image, see it with
lane/band boxes, Run detection off the UI thread, Export CSV + annotated PNG,
Save/Load JSON session.

**Owns / creates.**
- `packages/gel_app/src/gel_app/main.py` — `QApplication` bootstrap / Briefcase
  entry point.
- `packages/gel_app/src/gel_app/main_window.py` — menu/toolbar (Open, Run,
  Export, Save/Load Session), central canvas, minimal docks.
- `packages/gel_app/src/gel_app/canvas/` — `QGraphicsView`/`Scene`,
  `GelImageItem` (16-bit → 8-bit tone-mapped display), `LaneItem`/`BandItem`.
- `packages/gel_app/src/gel_app/controllers/` — owns the project model,
  mediates model↔widgets.
- `packages/gel_app/src/gel_app/workers.py` — `QThreadPool`/`QThread` wrapper
  calling `gel_core.run_pipeline`; results via queued signals.
- `packages/gel_app/src/gel_app/adapters.py` — Qt-side concrete impls of
  `gel_core` `ImageReader`/`ProjectStore` Protocols.
- `packages/gel_app/src/gel_app/docks/` — minimal (at least a log/status area).

**Hard dependencies.** Subtask 2 (models/ports/serialization — frozen),
Subtask 4 (`run_pipeline` + core CSV export).

**Key spec.** Per `PLAN.md` §4:
- `LaneItem`/`BandItem` are **movable and deletable** (confirmed M1 scope —
  minimal drag/delete; full add/resize remains M2). Edits emit signals →
  controller updates model → marks `manual_edited`.
- `run_pipeline` runs on a `QThreadPool`/`QThread` worker; **never run
  OpenCV/SciPy on the UI thread**; results delivered via queued signals.
- `adapters.py` implements the core Protocols (filesystem reader, JSON sidecar
  store).
- **Annotated PNG rendering lives here** (Qt scene render — confirmed decision).
  CSV comes from `gel_core` (Subtask 4). Save/Load JSON via
  `gel_core.serialization`.
- No CV/business logic in widgets — it lives in controllers/core.

**Acceptance criteria.**
- App launches via `uv run python -m gel_app` and shows the bundled sample.
- Clicking Run executes `run_pipeline` on a worker thread; UI stays responsive
  (no SciPy/OpenCV call on the main thread).
- Lane/band boxes render over the image after Run and can be moved/deleted.
- Export writes a CSV and an annotated PNG to disk.
- Save Session writes a JSON sidecar; Load Session reconstructs the project
  (round-trips through `gel_core.serialization`).

**Out of scope.** Box add/resize, undo/redo, multi-image project UX (all M2+).

---

### Subtask 7 — GUI smoke tests (pytest-qt, headless)

**Objective.** Headless test proving the click-path end-to-end.

**Owns / creates.** `tests/app/test_smoke.py` (+ `tests/app/conftest.py` if
needed for the offscreen platform fixture).

**Hard dependencies.** Subtask 6 (GUI must exist), Subtask 1 (pytest-qt
declared, sample image).

**Key spec.** Per `PLAN.md` §7 GUI smoke tests: under pytest-qt with
`QT_QPA_PLATFORM=offscreen` — instantiate main window; open the bundled sample;
trigger Run and drive the worker to completion via `qtbot.waitSignal`; assert
lane/band items exist on the scene; trigger Export and assert CSV + PNG land on
disk; Save then Load and assert the project round-trips; assert results arrive
via signal (worker ran off the main thread).

**Acceptance criteria.**
- `QT_QPA_PLATFORM=offscreen uv run pytest tests/app` green with no display.
- No flakiness across two runs (proper `waitSignal`/`waitUntil`, no bare
  sleeps).

**Out of scope.** Visual/pixel regression testing.

---

### Subtask 8 — CI workflow + macOS packaging spike (risk #1)

**Objective.** GitHub Actions CI green on Python 3.11, plus the M1 Briefcase
packaging spike scoped to this single-OS sandbox.

**Owns / creates.**
- `.github/workflows/ci.yml`
- Briefcase `[tool.briefcase]` config fleshed into
  `packages/gel_app/pyproject.toml` (replacing the Subtask 1 placeholder).
- `docs/packaging-spike.md`

**Hard dependencies.** Subtask 1 (deps declared — enough for the ci.yml file and
the import-only Briefcase probe). CI goes **fully green only after Subtasks 2–7
merge**; the full-GUI bundle launch needs Subtask 6.

**Key spec.**
- CI on **Python 3.11 only**: `uv sync`; `ruff check`; `ruff format --check`;
  `mypy packages/gel_core/src` (isolation) + full `mypy`; `pytest tests/core`;
  `pytest tests/app` with `QT_QPA_PLATFORM=offscreen`; the architecture guard
  test. CI runs on Linux runners — Qt offscreen + headless wheels must work
  there (`opencv-python-headless` was chosen partly for this).
- Spike per `PLAN.md` §6 risk #1, scoped to single-OS: `briefcase build` /
  `briefcase run` → an **unsigned** launchable macOS bundle that imports the
  full native stack (cv2 + scipy + skimage + PySide6) offline. **No
  notarization** in M1 (stays M5). An import-only Briefcase probe can run early
  (needs only Subtask 1) to de-risk wheel packaging independently of the GUI.
- `docs/packaging-spike.md` records: the macOS result; the
  `opencv-python-headless` (core) vs full (app) decision; a PyInstaller fallback
  recipe; and the deferred Windows/Linux plan with the exact commands a future
  operator runs on those OSes.

**Acceptance criteria.**
- Workflow file is valid and, once Waves 1–4 land, every job is green on
  Python 3.11.
- `briefcase build` + `briefcase run` produce a launchable **unsigned** macOS
  app bundle that imports the full native stack offline (import-probe must
  succeed even before the full GUI; full-GUI launch is the stronger bar once
  Subtask 6 lands).
- `docs/packaging-spike.md` is complete (macOS result, OpenCV decision,
  PyInstaller fallback, deferred Win/Linux commands).
- The architecture guard test is wired into CI and gating.

**Out of scope.** macOS notarization / code-signing (M5). Windows/Linux
installer builds (M5 — documented only). Python version matrix (M5).

---

## Part C — Wave / dependency map

```
WAVE 0   S1  Scaffold + deps + synthetic sample image            [TOTAL GATE]

WAVE 1   S2  Core contract (FREEZE)        ‖   S8a  import-only Briefcase probe
         ───── HUMAN CHECKPOINT: review S2 frozen API before fan-out ─────

WAVE 2   S3  Image I/O backend             ‖   S5   Architecture guard test

WAVE 3   S4  Pipeline + CSV + golden tests                  (needs S2, S3)

WAVE 4   S6  GUI app (drag/delete, export, save/load)       (needs S2, S4)

WAVE 5   S7  GUI smoke tests               ‖   S8b  CI green + full macOS bundle
```

- **Critical path:** S1 → S2 → S3 → S4 → S6 → S7/S8b (≈6 sequential stages).
- **Free parallelism:** S8a hides under Wave 1; S5 under Wave 2; S7 + S8b in
  Wave 5. S4 and S6 are unavoidably solo on the critical path (each is large).
- **Gates:** S1 is a total gate. S2 is the contract gate with a human checkpoint.
  S6 is a sub-gate for S7 and the full-GUI half of S8.
- **Shared artifact note:** the synthetic sample image (S1) is consumed by S3,
  S4, S6, S7 and the manual run. It is created once in Wave 0 at two
  byte-identical paths with a seeded generator so golden tolerances and the
  hardcoded ladder stay stable. Do not regenerate or relocate it in later
  subtasks.

---

## Part D — End-to-end verification path

Run in order; each step gates the next.

1. **Post-S1:** `uv sync`; `uv run python -c "import gel_core, gel_app"`;
   `uv run python tests/data/make_sample.py` twice → identical checksum.
2. **Post-S2:** `uv run mypy packages/gel_core/src` (isolation) green;
   `uv run pytest tests/core/test_serialization.py` green (round-trip lossless;
   checksum-mismatch warns; bad schema_version raises).
3. **Post-S4:** `uv run pytest tests/core` green — every stage golden +
   `run_pipeline` e2e golden stable across two runs; purity asserts (input
   arrays unmutated) pass.
4. **Post-S5:** `uv run pytest tests/core/test_architecture_guard.py` green;
   demonstrate it fails on an injected `import PySide6` (scratch, not committed).
5. **Post-S7:** `QT_QPA_PLATFORM=offscreen uv run pytest tests/app` green —
   open→run→items→export→save→load; CSV+PNG+JSON on disk; no SciPy/OpenCV on
   the UI thread.
6. **Post-S8:** `uv run ruff check` + `uv run ruff format --check` + full
   `uv run mypy` green locally and in CI on Python 3.11.
7. **Manual acceptance:** launch the app, open the bundled sample, click Run,
   see lane/band boxes, drag/delete one, Calibrate (hardcoded ladder), Export,
   then reload the saved session and confirm it reconstructs.
8. **Packaging:** `briefcase build` + `briefcase run` on macOS offline → the
   unsigned bundle launches and imports the full native stack;
   `docs/packaging-spike.md` complete.

**M1 is done** when steps 1–8 pass and a human signs off on the manual
acceptance run (step 7).
