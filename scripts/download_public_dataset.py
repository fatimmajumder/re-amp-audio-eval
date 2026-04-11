from __future__ import annotations

import argparse
import json
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.public_datasets import PUBLIC_DATASET_REGISTRY

AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a public audio dataset for RE-AMP smoke tests.")
    parser.add_argument("--dataset", required=True, help="Dataset id from the public registry.")
    parser.add_argument(
        "--output-root",
        default="data/public_datasets",
        help="Root directory for extracted datasets and manifests.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=16,
        help="Maximum number of audio files to extract from the archive.",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the downloaded archive after extraction.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_lookup = {dataset.dataset_id: dataset for dataset in PUBLIC_DATASET_REGISTRY}
    dataset = dataset_lookup.get(args.dataset)
    if not dataset:
        raise SystemExit(f"Unknown dataset id: {args.dataset}")

    if dataset.access_mode != "direct":
        raise SystemExit(
            f"{dataset.name} uses access mode '{dataset.access_mode}'. Open {dataset.source_url} for access instructions."
        )

    output_root = Path(args.output_root).resolve()
    dataset_root = output_root / dataset.dataset_id
    dataset_root.mkdir(parents=True, exist_ok=True)

    archive_name = Path(urlparse(dataset.download_url).path).name or f"{dataset.dataset_id}.archive"
    archive_path = dataset_root / archive_name

    print(f"Downloading {dataset.name} from {dataset.download_url}")
    with httpx.stream("GET", dataset.download_url, follow_redirects=True, timeout=1200.0) as response:
        response.raise_for_status()
        with archive_path.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)

    extracted_files = extract_archive(archive_path, dataset_root, max_files=args.max_files)
    manifest = {
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.name,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "source_url": dataset.source_url,
        "download_url": dataset.download_url,
        "license_name": dataset.license_name,
        "local_path": str(dataset_root),
        "audio_file_count": len(extracted_files),
        "sample_files": extracted_files[: min(len(extracted_files), 8)],
        "max_files": args.max_files,
    }
    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    if not args.keep_archive and archive_path.exists():
        archive_path.unlink()

    print(f"Wrote manifest to {manifest_path}")
    print(f"Extracted {len(extracted_files)} audio files")
    return 0


def extract_archive(archive_path: Path, destination: Path, *, max_files: int) -> list[str]:
    if archive_path.suffix == ".zip":
        return _extract_zip(archive_path, destination, max_files=max_files)

    if archive_path.suffixes[-2:] == [".tar", ".gz"] or archive_path.suffixes[-1:] == [".tgz"]:
        return _extract_tar(archive_path, destination, max_files=max_files)

    raise SystemExit(f"Unsupported archive format: {archive_path.name}")


def _extract_zip(archive_path: Path, destination: Path, *, max_files: int) -> list[str]:
    extracted: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if not _should_extract_audio(member.filename):
                continue
            archive.extract(member, destination)
            extracted.append(member.filename)
            if max_files and len(extracted) >= max_files:
                break
    return extracted


def _extract_tar(archive_path: Path, destination: Path, *, max_files: int) -> list[str]:
    extracted: list[str] = []
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if not _should_extract_audio(member.name):
                continue
            archive.extract(member, destination)
            extracted.append(member.name)
            if max_files and len(extracted) >= max_files:
                break
    return extracted


def _should_extract_audio(member_name: str) -> bool:
    path = Path(member_name)
    if path.suffix.lower() not in AUDIO_SUFFIXES:
        return False
    if any(part == "__MACOSX" for part in path.parts):
        return False
    if path.name.startswith("._"):
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
