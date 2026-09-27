from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request
import zipfile


URL = (
    "https://zenodo.org/records/8278563/files/"
    "posebusters_paper_data.zip"
)
EXPECTED_MD5 = "f004ac7c4e68317b5348497d2bb6bee6"


def digest_md5(path: Path) -> str:
    checksum = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def fetch_and_extract(
    destination: Path,
    *,
    keep_archive: bool = False,
) -> Path:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "posebusters_paper_data.zip"

    if not archive.exists():
        with urllib.request.urlopen(URL) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)

    actual = digest_md5(archive)
    if actual != EXPECTED_MD5:
        raise RuntimeError(
            f"dataset archive checksum mismatch: {actual}"
        )

    with zipfile.ZipFile(archive) as handle:
        handle.extractall(destination)

    if not keep_archive:
        archive.unlink()

    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--keep-archive", action="store_true")
    args = parser.parse_args()

    destination = fetch_and_extract(
        args.destination,
        keep_archive=args.keep_archive,
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
