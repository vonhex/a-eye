from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from PIL import Image

from backend.image_io import open_image

logger = logging.getLogger(__name__)


def _generate_thumbnail_sync(
    source_path: Path,
    thumb_path: Path,
    max_size: int,
    quality: int,
) -> Path | None:
    """CPU/IO-bound thumbnail work — runs in a thread pool, not the event loop."""
    try:
        img = open_image(source_path)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        img.save(thumb_path, "JPEG", quality=quality)
        return thumb_path
    except Exception:
        logger.warning("Failed to generate thumbnail for %s", source_path, exc_info=True)
        return None


async def get_or_create_thumbnail(
    image_id: int,
    source_path: Path,
    data_dir: Path,
    max_size: int = 400,
    quality: int = 80,
) -> Path | None:
    """Return the path to a cached thumbnail, generating it if needed.

    Thumbnails are stored in {data_dir}/thumbnails/{image_id}.jpg.
    Returns None if the source image can't be read.
    """
    thumbs_dir = data_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    thumb_path = thumbs_dir / f"{image_id}.jpg"

    if thumb_path.exists():
        return thumb_path

    # Run PIL work in a thread so it doesn't block the async event loop
    result = await asyncio.to_thread(
        _generate_thumbnail_sync, source_path, thumb_path, max_size, quality
    )
    if result:
        logger.debug("Generated thumbnail for image %d at %s", image_id, thumb_path)
    return result


async def delete_thumbnail(image_id: int, data_dir: Path) -> None:
    """Delete a cached thumbnail if it exists."""
    thumb_path = data_dir / "thumbnails" / f"{image_id}.jpg"
    if thumb_path.exists():
        thumb_path.unlink()
        logger.debug("Deleted thumbnail for image %d", image_id)


async def prune_orphaned_thumbnails(
    data_dir: Path, valid_image_ids: set[int]
) -> int:
    """Delete thumbnails that don't correspond to any known image ID.

    Returns the count of pruned files.
    """
    thumbs_dir = data_dir / "thumbnails"
    if not thumbs_dir.exists():
        return 0

    pruned = 0
    for thumb_file in thumbs_dir.glob("*.jpg"):
        try:
            file_id = int(thumb_file.stem)
            if file_id not in valid_image_ids:
                thumb_file.unlink()
                pruned += 1
        except ValueError:
            # Filename isn't a number — shouldn't be here, clean it up
            thumb_file.unlink()
            pruned += 1

    if pruned:
        logger.info("Pruned %d orphaned thumbnails", pruned)
    return pruned
