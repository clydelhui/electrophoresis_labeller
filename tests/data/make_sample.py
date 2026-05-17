"""Deterministic synthetic gel image generator (canonical M1 sample).

This script is the *single source of truth* for the synthetic gel used by the
whole test suite and by the bundled app resource. It is consumed by Subtasks
3, 4, 6, 7 and the manual acceptance run. Do not regenerate or relocate the
output in later subtasks; the module-level constants below (lane x-centers,
ladder band y-centers, ladder known sizes) are mirrored by Subtasks 2 and 4
as golden tolerances and the hardcoded ladder.

Image characterization (user-confirmed, frozen contract):

* 16-bit grayscale (``uint16``), ``IMAGE_WIDTH`` x ``IMAGE_HEIGHT``.
* 6 vertical lanes; lane ``LADDER_LANE_INDEX`` (0, leftmost) is the LADDER
  with 5 well-separated bands; the other 5 are sample lanes with 2-4 bands.
* Polarity: **bright bands on a dark background** (fluorescence-style).
  Pixel value increases with band signal; background is near-black.
* Geometry: wells are at the top (small y). Migration proceeds downward
  (increasing y). Larger y therefore means a *smaller* DNA fragment.
* Ladder is a **DNA size ladder in base pairs** (``LADDER_KNOWN_BP``). Band
  y-centers are placed linearly in ``log10(size_bp)`` so a log-linear
  calibration fits with r^2 ~= 1.0.

Determinism: all randomness comes from ``numpy.random.default_rng(SEED)``
(PCG64, stream-stable across platforms). Pure numpy only — no scikit-image,
OpenCV or BLAS-backed ops touch the array (avoids nondeterminism). The TIFF
is encoded once in memory with metadata/Software tags suppressed, then the
identical byte buffer is written to both output paths, guaranteeing the two
files are byte-identical and stable across runs.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
import tifffile
from numpy.typing import NDArray

SEED: int = 20260518

IMAGE_WIDTH: int = 480
IMAGE_HEIGHT: int = 640

# 6 lanes evenly spaced with a 40 px margin on each side.
LANE_X_CENTERS: list[int] = [40, 120, 200, 280, 360, 440]

LADDER_LANE_INDEX: int = 0

# DNA size ladder, base pairs (descending — largest fragment migrates least).
LADDER_KNOWN_BP: list[float] = [10000.0, 3000.0, 1000.0, 500.0, 100.0]

# Band y-centers placed linearly in log10(size_bp): y = -220*log10(bp) + 980,
# rounded to int. Largest fragment (10000 bp) sits near the wells (top),
# smallest (100 bp) near the bottom. Mirrored by Subtasks 2 & 4.
LADDER_Y_CENTERS: list[int] = [100, 215, 320, 386, 540]

_LANE_SIGMA_X: float = 14.0
_BAND_SIGMA_Y: float = 6.0
_BACKGROUND: float = 800.0
_NOISE_SIGMA: float = 150.0
_MAX_UINT16: int = 65535


def _add_band(
    image: NDArray[np.float64],
    xx: NDArray[np.float64],
    yy: NDArray[np.float64],
    x_center: float,
    y_center: float,
    amplitude: float,
) -> None:
    """Add one 2-D Gaussian band blob to ``image`` in place."""
    gx = (xx - x_center) ** 2 / (2.0 * _LANE_SIGMA_X**2)
    gy = (yy - y_center) ** 2 / (2.0 * _BAND_SIGMA_Y**2)
    image += amplitude * np.exp(-(gx + gy))


def build_image() -> NDArray[np.uint16]:
    """Build the deterministic synthetic gel as a uint16 array."""
    rng = np.random.default_rng(SEED)

    image: NDArray[np.float64] = np.full((IMAGE_HEIGHT, IMAGE_WIDTH), _BACKGROUND, dtype=np.float64)
    grid_y, grid_x = np.mgrid[0:IMAGE_HEIGHT, 0:IMAGE_WIDTH]
    xx = grid_x.astype(np.float64)
    yy = grid_y.astype(np.float64)

    for lane_index, x_center in enumerate(LANE_X_CENTERS):
        if lane_index == LADDER_LANE_INDEX:
            for y_center in LADDER_Y_CENTERS:
                amplitude = float(rng.uniform(34000.0, 46000.0))
                _add_band(image, xx, yy, float(x_center), float(y_center), amplitude)
            continue

        n_bands = int(rng.integers(2, 5))  # 2, 3 or 4 bands
        y_centers = np.sort(rng.uniform(120.0, 560.0, size=n_bands))
        for y_center in y_centers:
            amplitude = float(rng.uniform(15000.0, 50000.0))
            _add_band(image, xx, yy, float(x_center), float(y_center), amplitude)

    image += rng.normal(0.0, _NOISE_SIGMA, size=image.shape)

    quantized = np.clip(np.rint(image), 0.0, float(_MAX_UINT16))
    return quantized.astype(np.uint16)


def _output_paths() -> list[Path]:
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    return [
        here.parent / "sample_gel.tif",
        repo_root / "packages" / "gel_app" / "src" / "gel_app" / "resources" / "sample_gel.tif",
    ]


def encode_tiff(image: NDArray[np.uint16]) -> bytes:
    """Encode ``image`` to reproducible TIFF bytes.

    ``metadata=None`` suppresses the JSON/ImageJ/OME ImageDescription and
    ``software=False`` suppresses the version-dependent Software tag — the two
    tags that would otherwise break byte-identity across runs/versions.
    tifffile writes no DateTime tag by default.
    """
    buf = io.BytesIO()
    tifffile.imwrite(
        buf,
        image,
        photometric="minisblack",
        metadata=None,
        software=False,
    )
    return buf.getvalue()


def main() -> None:
    image = build_image()
    data = encode_tiff(image)
    for path in _output_paths():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
