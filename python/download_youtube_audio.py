#!/usr/bin/env python3
"""Download audio tracks from YouTube links listed in a JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

from yt_dlp import YoutubeDL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download audio from YouTube links in a JSON file"
    )
    parser.add_argument(
        "--json-file",
        default="youtube_links.json",
        help="Path to JSON file that contains YouTube links",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory where downloaded audio files are saved (overrides JSON output_dir)",
    )
    parser.add_argument(
        "--audio-format",
        default="mp3",
        choices=["mp3", "m4a", "wav", "opus", "vorbis", "flac"],
        help="Audio format for output files",
    )
    parser.add_argument(
        "--audio-quality",
        default="192",
        help="Target audio quality for ffmpeg extraction (for example: 128, 192, 256)",
    )
    return parser.parse_args()


def unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_urls(payload) -> List[str]:
    # Supported structures:
    # 1) ["url1", "url2"]
    # 2) {"videos": ["url1", "url2"]}
    # 3) {"links": ["url1", "url2"]}
    # 4) {"urls": ["url1", "url2"]}
    # 5) {"videos": [{"url": "url1"}, {"link": "url2"}]}
    candidates: List[str] = []

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                candidates.append(item.strip())
        return unique_preserve_order([u for u in candidates if u])

    if not isinstance(payload, dict):
        raise ValueError("JSON must be either a list or an object")

    source = None
    for key in ("videos", "links", "urls"):
        if key in payload:
            source = payload[key]
            break

    if source is None or not isinstance(source, list):
        raise ValueError("JSON object must contain one of these list keys: videos, links, urls")

    for item in source:
        if isinstance(item, str):
            item = item.strip()
            if item:
                candidates.append(item)
            continue

        if isinstance(item, dict):
            for field in ("url", "link"):
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
                    break

    return unique_preserve_order(candidates)


def extract_output_dir(payload) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ("output_dir", "audio_output_dir"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def load_urls_and_output_dir(json_file: Path) -> tuple[List[str], str | None]:
    if not json_file.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")

    with json_file.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    urls = extract_urls(payload)
    if not urls:
        raise ValueError("No valid YouTube URLs found in JSON file")
    output_dir = extract_output_dir(payload)
    return urls, output_dir


def download_all(urls: List[str], output_dir: Path, audio_format: str, audio_quality: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / "%(title)s [%(id)s].%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "ignoreerrors": True,
        "quiet": False,
        "no_warnings": False,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": audio_quality,
            }
        ],
    }

    failures = 0
    with YoutubeDL(ydl_opts) as ydl:
        for index, url in enumerate(urls, start=1):
            print(f"[{index}/{len(urls)}] Downloading: {url}")
            try:
                result_code = ydl.download([url])
                if result_code != 0:
                    failures += 1
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"Failed: {url}\nReason: {exc}", file=sys.stderr)

    return failures


def main() -> int:
    args = parse_args()
    json_file = Path(args.json_file).expanduser().resolve()

    try:
        urls, output_dir_from_json = load_urls_and_output_dir(json_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Error loading URLs: {exc}", file=sys.stderr)
        return 1

    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
    elif output_dir_from_json:
        output_dir = Path(output_dir_from_json).expanduser()
    else:
        output_dir = Path("audio")

    if not output_dir.is_absolute():
        output_dir = json_file.parent / output_dir
    output_dir = output_dir.resolve()

    failures = download_all(
        urls=urls,
        output_dir=output_dir,
        audio_format=args.audio_format,
        audio_quality=args.audio_quality,
    )

    success_count = len(urls) - failures
    print(f"\nCompleted. Success: {success_count}, Failed: {failures}, Total: {len(urls)}")
    print(f"Saved files in: {output_dir}")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
