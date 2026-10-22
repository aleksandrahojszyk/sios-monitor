from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .usability import (
    DEFAULT_USABILITY_SQLITE,
    USABILITY_EXPORT_DIR,
    export_usability_session,
    normalize_participant_id,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export usability-test events and a simple per-session summary CSV."
    )
    parser.add_argument(
        "--participant",
        default=None,
        help="Participant identifier, e.g. P01. Omit to export all participants.",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=DEFAULT_USABILITY_SQLITE,
        help="Isolated usability SQLite (default: data/usability/inbox.sqlite)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=USABILITY_EXPORT_DIR,
        help="Directory for CSV files (default: data/usability/)",
    )
    args = parser.parse_args(argv)
    participant = None
    if args.participant:
        try:
            participant = normalize_participant_id(args.participant)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
    try:
        paths = export_usability_session(
            args.sqlite,
            participant_id=participant,
            out_dir=args.out_dir,
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Events: {}".format(paths["events"]))
    print("Summary: {}".format(paths["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
