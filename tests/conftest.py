"""Shared pytest fixtures for the electrophoresis-labeller test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_image_path() -> Path:
    """Path to the canonical synthetic gel image (see tests/data/make_sample.py)."""
    return Path(__file__).parent / "data" / "sample_gel.tif"
