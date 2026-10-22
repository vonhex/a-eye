from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException

from backend.filename import ensure_unique
from backend.watcher import IMAGE_EXTENSIONS
from backend.pathsafe import confine

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 64  # 64KB

router = APIRouter()


@router.post("/upload")
async def api_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    subfolder: str = Form(""),
):
    """Upload image files to the photos directory for normal processing."""
    settings = request.app.state.settings
    photos_readonly = getattr(request.app.state, "photos_readonly", False)
    if photos_readonly or settings.catalogue_mode:
        raise HTTPException(403, "Uploads disabled in catalogue mode")
    photos_dir = Path(settings.photos_dir)

    # Resolve subfolder safely
    if subfolder:
        try:
            dest_dir = confine(photos_dir, subfolder)
        except ValueError:
            raise HTTPException(400, "Invalid subfolder path")
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        dest_dir = photos_dir

    saved = 0
    skipped = 0

    for upload in files:
        if not upload.filename:
            skipped += 1
            continue

        # Sanitise: take only the basename (strip directory traversal)
        safe_name = Path(upload.filename).name.lstrip(".")
        if not safe_name:
            skipped += 1
            continue

        ext = Path(safe_name).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            skipped += 1
            continue

        target = ensure_unique(dest_dir / safe_name)
        max_bytes = settings.max_upload_size_mb * 1024 * 1024

        # Stream to disk with size limit
        try:
            total_bytes = 0
            with open(target, "wb") as f:
                while True:
                    chunk = await upload.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if max_bytes and total_bytes > max_bytes:
                        raise ValueError(f"File exceeds {settings.max_upload_size_mb}MB limit")
                    f.write(chunk)
            saved += 1
            logger.info("Uploaded: %s → %s", upload.filename, target.name)
        except ValueError as exc:
            logger.warning("Upload rejected %s: %s", upload.filename, exc)
            target.unlink(missing_ok=True)
            skipped += 1
        except OSError as exc:
            logger.error("Failed to save %s: %s", upload.filename, exc)
            target.unlink(missing_ok=True)
            skipped += 1

    return {"saved": saved, "skipped": skipped}
