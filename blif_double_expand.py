#!/usr/bin/env python3
"""
For each .blif under an input path, run ABC:
  read_blif <src>; double; ... (N times); write_blif <dst>

Each `double` roughly doubles the network size; N repeats => about 2^N x (set via -n/--doubles, default 5 => 32x).

Run from the repository root so ./tools/abc/abc resolves.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from utils import utils


def collect_blif_files(input_path: Path):
    """Single file -> one-element list; directory -> all .blif recursively."""
    input_path = input_path.resolve()
    if not input_path.exists():
        return None, None, "Path does not exist: {}".format(input_path)

    if input_path.is_file():
        if input_path.suffix.lower() != ".blif":
            return None, None, "Not a BLIF file: {}".format(input_path)
        return [input_path], input_path.parent, None

    if input_path.is_dir():
        found = sorted(input_path.rglob("*.blif"))
        return found, input_path, None

    return None, None, "Invalid path: {}".format(input_path)


def run_abc_double_expand(src: str, dst: str, num_doubles: int) -> str:
    """Run ABC read_blif, `double` x num_doubles, write_blif. Returns stdout."""
    chain = ["read_blif {}".format(src)]
    chain.extend(["double"] * num_doubles)
    chain.append("write_blif {}".format(dst))
    script = "; ".join(chain) + ";"
    cmd = './tools/abc/abc -c "{}"'.format(script)
    stdout, _elapsed = utils.run_command(cmd)
    if not os.path.isfile(dst):
        raise RuntimeError(
            "ABC did not create output. Command ended; missing: {}\n--- ABC output ---\n{}".format(
                dst, stdout
            )
        )
    return stdout


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-expand BLIF files with ABC `double`; repeat count is configurable (-n/--doubles)."
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to one .blif file or a directory (recursive *.blif).",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Root directory for expanded .blif files (mirrors relative paths under input).",
    )
    parser.add_argument(
        "-n",
        "--doubles",
        type=int,
        default=5,
        metavar="N",
        dest="doubles",
        help="How many times to run ABC `double` after read_blif (default: 5 => ~2^5=32x). Use 0 for no double.",
    )
    args = parser.parse_args()

    if args.doubles < 0:
        print("Error: --doubles must be >= 0", file=sys.stderr)
        sys.exit(1)

    blif_list, scan_root, err = collect_blif_files(Path(args.input))
    if err:
        print("Error: {}".format(err), file=sys.stderr)
        sys.exit(1)
    if not blif_list:
        print("No .blif files found under: {}".format(args.input), file=sys.stderr)
        sys.exit(1)

    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    n_ok = 0
    for blif_path in blif_list:
        rel = blif_path.resolve().relative_to(scan_root.resolve())
        dst_path = out_root / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_s = str(blif_path.resolve())
        dst_s = str(dst_path.resolve())

        sys.stdout.write("[{}/{}] {} -> {}\n".format(n_ok + 1, len(blif_list), rel, dst_path))
        sys.stdout.flush()
        try:
            run_abc_double_expand(src_s, dst_s, args.doubles)
        except Exception as ex:
            print("Error: {}".format(ex), file=sys.stderr)
            sys.exit(1)
        n_ok += 1

    scale = 2 ** args.doubles
    print(
        "Done. {} file(s) written under {} ({} `double` step(s) each, 2^{} = {}x).".format(
            n_ok, out_root, args.doubles, args.doubles, scale
        )
    )


if __name__ == "__main__":
    main()
