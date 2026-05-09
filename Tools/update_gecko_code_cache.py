#!/usr/bin/env python3
"""Regenerate the Android bundled Gecko code cache from the RC24 mirror."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
import urllib.error
import urllib.request
import zipfile


ENDPOINT = "https://codes.rc24.xyz/txt.php?txt={game_id}"
USER_AGENT = "DolphinAndroidGeckoCache/1.0"


def read_game_ids(wiitdb_path: Path) -> list[str]:
    game_ids: set[str] = set()
    for line in wiitdb_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if " = " not in line:
            continue
        game_id = line.split(" = ", 1)[0].strip().upper()
        if len(game_id) == 6 and game_id.isalnum():
            game_ids.add(game_id)
    return sorted(game_ids)


def fetch_code_text(game_id: str, timeout: int) -> str | None:
    request = urllib.request.Request(
        ENDPOINT.format(game_id=game_id),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise

    first_line = text.splitlines()[0].strip().upper() if text.splitlines() else ""
    return text if first_line == game_id else None


def build_cache(repo: Path, workers: int, timeout: int) -> tuple[int, int, int]:
    game_ids = read_game_ids(repo / "Data/Sys/wiitdb-en.txt")
    output = repo / "Data/Sys/GeckoCodes.zip"
    output.parent.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    texts: dict[str, str] = {}

    def fetch(game_id: str) -> tuple[str, str | None]:
        return game_id, fetch_code_text(game_id, timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for game_id, text in executor.map(fetch, game_ids):
            if text:
                texts[game_id] = text

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(
            "SOURCE.txt",
            "\n".join(
                [
                    "Bundled Gecko code cache for the Android fork.",
                    f"Generated UTC: {generated_at}",
                    f"Entries: {len(texts)}",
                    f"Seed IDs: {len(game_ids)} from Data/Sys/wiitdb-en.txt",
                    f"Source template: {ENDPOINT}",
                    "Upstream provenance: the RC24 mirror homepage states all codes come from GameHacking.org.",
                    "",
                ]
            ),
        )
        for game_id in sorted(texts):
            zf.writestr(f"{game_id}.txt", texts[game_id])

    readme = output.with_suffix(".README.txt")
    readme.write_text(
        "\n".join(
            [
                "Bundled Gecko code cache for this Android fork.",
                "",
                f"Source template: {ENDPOINT}",
                "Upstream provenance: the RC24 mirror homepage states all codes come from GameHacking.org.",
                "Game ID seed list: Data/Sys/wiitdb-en.txt.",
                "",
                f"Generated entries: {len(texts)}",
                f"Generated UTC: {generated_at}",
                "",
                "Regenerate with Tools/update_gecko_code_cache.py.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    return len(game_ids), len(texts), output.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    seed_count, entry_count, byte_count = build_cache(args.repo, args.workers, args.timeout)
    print(f"seed_ids={seed_count} entries={entry_count} zip_bytes={byte_count}")


if __name__ == "__main__":
    main()
