"""CLI test script for the A-Eye pipeline.

Usage:
    python -m backend.cli_test /path/to/image.jpg
    python -m backend.cli_test /path/to/image.jpg --ollama-host http://localhost:11434
    python -m backend.cli_test /path/to/image.jpg --llm-model qwen3:14b  # enable two-model mode
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from backend.config import Settings
from backend.ollama_client import make_ai_client
from backend.pipeline import process_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the A-Eye pipeline on an image")
    parser.add_argument("image", type=Path, help="Path to an image file")
    parser.add_argument("--ollama-host", default=None, help="Ollama API URL (default: from env/settings)")
    parser.add_argument("--vision-model", default=None, help="Vision model name")
    parser.add_argument("--llm-model", default=None, help="LLM model name (enables two-model mode)")
    parser.add_argument("--template", default=None, help="Filename template")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.image.exists():
        print(f"Error: File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    if not args.image.is_file():
        print(f"Error: Not a file: {args.image}", file=sys.stderr)
        sys.exit(1)

    # Build settings with CLI overrides
    overrides = {}
    if args.ollama_host:
        overrides["ollama_host"] = args.ollama_host
    if args.vision_model:
        overrides["vision_model"] = args.vision_model
    if args.llm_model:
        overrides["llm_model"] = args.llm_model
    if args.template:
        overrides["filename_template"] = args.template

    settings = Settings(**overrides)

    print(f"Image:        {args.image}")
    print(f"Ollama host:  {settings.ollama_host}")
    print(f"Vision model: {settings.vision_model}")
    print(f"LLM model:    {settings.llm_model or '(none — single-model mode)'}")
    print(f"Template:     {settings.filename_template}")
    print()

    asyncio.run(_run(args.image, settings))


async def _run(image_path: Path, settings: Settings) -> None:
    ollama = make_ai_client(settings)

    try:
        # Check connection first
        connected = await ollama.check_connection()
        if not connected:
            print(f"Error: Cannot connect to Ollama at {settings.ollama_host}", file=sys.stderr)
            sys.exit(1)
        print("Ollama connection: OK")

        # List available models
        models = await ollama.list_models()
        model_names = [m.get("name", "?") for m in models]
        print(f"Available models: {', '.join(model_names)}")
        print()

        # Run the pipeline
        print("Processing image...")
        result = await process_image(image_path, settings, ollama)

        # Display results
        print()
        print("=" * 60)
        print("PIPELINE RESULTS")
        print("=" * 60)

        if result.metadata:
            print(f"\n--- Stage 1: Metadata ---")
            print(f"  Date:     {result.metadata.date or '(none)'}")
            print(f"  GPS:      {result.metadata.gps_lat}, {result.metadata.gps_lon}"
                  if result.metadata.gps_lat else "  GPS:      (none)")
            print(f"  Location: {result.location_name or '(none)'}")
            print(f"  Camera:   {result.metadata.camera_model or '(none)'}")

        print(f"\n--- Stage 2: Vision ---")
        print(f"  Description: {result.vision_description}")

        print(f"\n--- Final Result ---")
        print(f"  Proposed filename: {result.final_filename}")
        print(f"  Confidence score:  {result.confidence_score:.2f}")

        if result.error:
            print(f"\n  ERROR: {result.error}")

        # Full EXIF dump (verbose)
        if result.metadata and result.metadata.raw:
            print(f"\n--- Raw EXIF (first 20 tags) ---")
            for i, (k, v) in enumerate(result.metadata.raw.items()):
                if i >= 20:
                    print(f"  ... and {len(result.metadata.raw) - 20} more")
                    break
                print(f"  {k}: {v}")

    finally:
        await ollama.close()


if __name__ == "__main__":
    main()
