from __future__ import annotations

import logging
import re
from backend.pathsafe import confine
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/folders")
async def list_folders(
    request: Request,
    max_depth: int = Query(10, ge=1, le=50),
):
    """Return the directory tree under photos_dir as nested JSON."""
    settings = request.app.state.settings
    photos_dir = Path(settings.photos_dir)

    if not photos_dir.exists() or not photos_dir.is_dir():
        return {"tree": [], "photos_dir": settings.photos_dir}

    photos_resolved = photos_dir.resolve()

    def build_tree(base: Path, relative_prefix: str = "", depth: int = 0) -> list[dict]:
        if depth >= max_depth:
            return []
        entries = []
        try:
            children = sorted(
                [d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")],
                key=lambda d: d.name.lower(),
            )
        except PermissionError:
            return entries

        for child in children:
            # Skip symlinks that escape photos_dir
            if child.is_symlink():
                try:
                    child.resolve().relative_to(photos_resolved)
                except ValueError:
                    continue

            rel_path = f"{relative_prefix}/{child.name}".lstrip("/")
            node = {
                "name": child.name,
                "path": rel_path,
                "children": build_tree(child, rel_path, depth + 1),
            }
            entries.append(node)
        return entries

    children = build_tree(photos_dir)
    root_name = photos_dir.name or "photos"
    virtual_root_files = {"name": "(root files)", "path": "__root_files__", "children": []}
    root = {"name": root_name, "path": ".", "children": [virtual_root_files] + children}
    return {"tree": [root], "photos_dir": settings.photos_dir}


class CreateFolderRequest(BaseModel):
    parent: str = ""
    name: str


@router.post("/folders")
async def create_folder(request: Request, body: CreateFolderRequest):
    """Create a new subfolder under photos_dir."""
    settings = request.app.state.settings
    photos_readonly = getattr(request.app.state, "photos_readonly", False)
    if photos_readonly or settings.catalogue_mode:
        raise HTTPException(403, "Folder creation disabled in catalogue mode")
    photos_dir = Path(settings.photos_dir)
    name = body.name.strip()

    if not name:
        raise HTTPException(400, "Folder name cannot be empty")
    if name.startswith("."):
        raise HTTPException(400, "Folder name cannot start with a dot")
    if "/" in name or "\\" in name:
        raise HTTPException(400, "Folder name cannot contain path separators")
    if not re.match(r'^[\w\s\-\.]+$', name):
        raise HTTPException(400, "Folder name contains invalid characters")

    parent = body.parent.strip().strip("/")
    try:
        target = confine(photos_dir, parent, name) if parent and parent != "." else confine(photos_dir, name)
    except ValueError:
        raise HTTPException(400, "Invalid folder path")

    target.mkdir(parents=True, exist_ok=True)
    rel_path = str(target.relative_to(photos_dir.resolve()))
    logger.info("Created folder: %s", rel_path)
    return {"path": rel_path, "created": True}
