#!/usr/bin/env python3
"""Create a stop-motion video from a folder of images using a JSON config."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class Config:
    input_dir: Path
    output_file: Path
    fps: float
    frame_step: int
    image_extensions: List[str]
    sort_mode: str
    start_index: int
    end_index: int | None
    target_width: int | None
    target_height: int | None
    fit_mode: str
    background_color_bgr: Tuple[int, int, int]
    codec: str
    overwrite: bool
    postprocess_h264: bool
    ffmpeg_binary: str
    h264_crf: int
    h264_preset: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create stop-motion video from image sequence")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to JSON config file (default: config.json)",
    )
    return parser.parse_args()


def natural_key(path: Path) -> List[object]:
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def parse_config(path: Path) -> Config:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    config_dir = path.parent.resolve()

    input_dir = Path(raw["input_dir"]).expanduser()
    output_file = Path(raw["output_file"]).expanduser()

    if not input_dir.is_absolute():
        input_dir = config_dir / input_dir
    if not output_file.is_absolute():
        output_file = config_dir / output_file
    fps = float(raw.get("fps", 12))
    frame_step = int(raw.get("frame_step", 1))
    image_extensions = [str(ext).lower() for ext in raw.get("image_extensions", [".jpg", ".jpeg", ".png", ".webp"])]
    sort_mode = str(raw.get("sort_mode", "natural")).lower()
    start_index = int(raw.get("start_index", 0))

    end_index_raw = raw.get("end_index", None)
    end_index = None if end_index_raw is None else int(end_index_raw)

    target_width_raw = raw.get("target_width", None)
    target_height_raw = raw.get("target_height", None)
    target_width = None if target_width_raw is None else int(target_width_raw)
    target_height = None if target_height_raw is None else int(target_height_raw)

    fit_mode = str(raw.get("fit_mode", "contain")).lower()

    bg = raw.get("background_color_bgr", [0, 0, 0])
    if not isinstance(bg, list) or len(bg) != 3:
        raise ValueError("background_color_bgr must be a list of 3 integers")
    background_color_bgr = tuple(int(x) for x in bg)

    codec = str(raw.get("codec", "mp4v"))
    overwrite = bool(raw.get("overwrite", True))
    postprocess_h264 = bool(raw.get("postprocess_h264", False))
    ffmpeg_binary = str(raw.get("ffmpeg_binary", "ffmpeg"))
    h264_crf = int(raw.get("h264_crf", 18))
    h264_preset = str(raw.get("h264_preset", "medium"))

    if fps <= 0:
        raise ValueError("fps must be > 0")
    if frame_step <= 0:
        raise ValueError("frame_step must be > 0")
    if fit_mode not in {"contain", "cover", "stretch"}:
        raise ValueError("fit_mode must be one of: contain, cover, stretch")
    if sort_mode not in {"natural", "name", "mtime"}:
        raise ValueError("sort_mode must be one of: natural, name, mtime")
    if not (0 <= h264_crf <= 51):
        raise ValueError("h264_crf must be between 0 and 51")
    if h264_preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
        raise ValueError(
            "h264_preset must be one of: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow"
        )

    return Config(
        input_dir=input_dir,
        output_file=output_file,
        fps=fps,
        frame_step=frame_step,
        image_extensions=image_extensions,
        sort_mode=sort_mode,
        start_index=start_index,
        end_index=end_index,
        target_width=target_width,
        target_height=target_height,
        fit_mode=fit_mode,
        background_color_bgr=background_color_bgr,
        codec=codec,
        overwrite=overwrite,
        postprocess_h264=postprocess_h264,
        ffmpeg_binary=ffmpeg_binary,
        h264_crf=h264_crf,
        h264_preset=h264_preset,
    )


def collect_images(input_dir: Path, image_extensions: Sequence[str], sort_mode: str) -> List[Path]:
    images = [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in image_extensions]

    if sort_mode == "natural":
        images.sort(key=natural_key)
    elif sort_mode == "name":
        images.sort(key=lambda p: p.name.lower())
    else:
        images.sort(key=lambda p: p.stat().st_mtime)

    return images


def apply_range(images: Sequence[Path], start_index: int, end_index: int | None, frame_step: int) -> List[Path]:
    sliced = images[start_index:end_index:frame_step]
    return list(sliced)


def fit_frame(
    frame,
    target_width: int,
    target_height: int,
    fit_mode: str,
    background_color_bgr: Tuple[int, int, int],
):
    src_h, src_w = frame.shape[:2]

    if fit_mode == "stretch":
        return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)

    src_ratio = src_w / src_h
    target_ratio = target_width / target_height

    if fit_mode == "contain":
        if src_ratio > target_ratio:
            new_w = target_width
            new_h = max(1, int(round(target_width / src_ratio)))
        else:
            new_h = target_height
            new_w = max(1, int(round(target_height * src_ratio)))

        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        canvas = np.full((target_height, target_width, 3), background_color_bgr, dtype=np.uint8)
        x = (target_width - new_w) // 2
        y = (target_height - new_h) // 2
        canvas[y : y + new_h, x : x + new_w] = resized
        return canvas

    if src_ratio > target_ratio:
        new_h = target_height
        new_w = max(1, int(round(target_height * src_ratio)))
    else:
        new_w = target_width
        new_h = max(1, int(round(target_width / src_ratio)))

    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    x = (new_w - target_width) // 2
    y = (new_h - target_height) // 2
    return resized[y : y + target_height, x : x + target_width]


def read_first_valid_frame(images: Iterable[Path]):
    for path in images:
        frame = cv2.imread(str(path))
        if frame is not None:
            return frame
    return None


def reencode_to_h264(config: Config, source_path: Path, output_path: Path) -> None:
    if shutil.which(config.ffmpeg_binary) is None:
        raise RuntimeError(f"ffmpeg binary not found: {config.ffmpeg_binary}")

    cmd = [
        config.ffmpeg_binary,
        "-y",
        "-i",
        str(source_path),
        "-c:v",
        "libx264",
        "-preset",
        config.h264_preset,
        "-crf",
        str(config.h264_crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"ffmpeg re-encode failed: {stderr}")


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = parse_config(config_path)
    except Exception as exc:
        print(f"Invalid config: {exc}", file=sys.stderr)
        return 1

    if not config.input_dir.exists() or not config.input_dir.is_dir():
        print(f"Input directory does not exist: {config.input_dir}", file=sys.stderr)
        return 1

    images = collect_images(config.input_dir, config.image_extensions, config.sort_mode)
    selected = apply_range(images, config.start_index, config.end_index, config.frame_step)

    if not selected:
        print("No images found after applying filters/range.", file=sys.stderr)
        return 1

    first_frame = read_first_valid_frame(selected)
    if first_frame is None:
        print("No readable images in selected set.", file=sys.stderr)
        return 1

    if config.target_width is None or config.target_height is None:
        target_height, target_width = first_frame.shape[:2]
    else:
        target_width = config.target_width
        target_height = config.target_height

    if target_width <= 0 or target_height <= 0:
        print("target_width and target_height must be > 0", file=sys.stderr)
        return 1

    output_path = config.output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not config.overwrite:
        print(f"Output exists and overwrite=false: {output_path}", file=sys.stderr)
        return 1

    writer_output_path = output_path
    if config.postprocess_h264:
        writer_output_path = output_path.with_name(f"{output_path.stem}.__opencv_tmp__{output_path.suffix}")

    fourcc = cv2.VideoWriter_fourcc(*config.codec)
    writer = cv2.VideoWriter(str(writer_output_path), fourcc, config.fps, (target_width, target_height))

    if not writer.isOpened():
        print("Failed to open video writer. Check codec/output path.", file=sys.stderr)
        return 1

    frames_written = 0

    for path in selected:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"Skipping unreadable image: {path}", file=sys.stderr)
            continue

        processed = fit_frame(
            frame,
            target_width=target_width,
            target_height=target_height,
            fit_mode=config.fit_mode,
            background_color_bgr=config.background_color_bgr,
        )

        if processed.shape[1] != target_width or processed.shape[0] != target_height:
            print(f"Skipping frame with invalid dimensions after processing: {path}", file=sys.stderr)
            continue

        writer.write(processed)
        frames_written += 1

    writer.release()

    if frames_written == 0:
        print("No frames were written; output video may be invalid.", file=sys.stderr)
        return 1

    if config.postprocess_h264:
        try:
            reencode_to_h264(config, writer_output_path, output_path)
        except Exception as exc:
            print(f"H.264 post-process failed: {exc}", file=sys.stderr)
            return 1
        finally:
            if writer_output_path.exists():
                writer_output_path.unlink()

    print(f"Created: {output_path}")
    print(f"Frames written: {frames_written}")
    print(f"FPS: {config.fps}")
    print(f"Duration (approx): {frames_written / config.fps:.2f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
