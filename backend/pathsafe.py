"""Confine user-influenced paths to a base directory."""

from __future__ import annotations

import os
from pathlib import Path


def confine(base: str | Path, *parts: str | Path) -> Path:
    """Join parts onto base, resolve symlinks and '..', and refuse anything outside base.

    Raises ValueError when the resolved path escapes base.
    """
    base_real = os.path.realpath(base)
    full = os.path.realpath(os.path.join(base_real, *(str(p) for p in parts)))
    if full != base_real and not full.startswith(base_real + os.sep):
        raise ValueError(f"path escapes {base_real}")
    return Path(full)
