from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.sios.config import PROJECT_ROOT

from .usability import (
    DEFAULT_USABILITY_SQLITE,
    UsabilitySafetyError,
    prepare_usability_dataset,
    volunteer_sqlite_path,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy a small SIOS sample into an isolated usability SQLite file "
            "and add marked synthetic EkoKarty fixtures."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Collector SQLite (default: data/normalized/sios.sqlite)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_USABILITY_SQLITE,
        help="Isolated usability SQLite (default: data/usability/inbox.sqlite)",
    )
    args = parser.parse_args(argv)
    try:
        result = prepare_usability_dataset(
            source_sqlite=args.source,
            dest_sqlite=args.dest,
        )
    except (UsabilitySafetyError, FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Usability dataset ready")
    print("Source: {}".format(result["source"]))
    print("Dest: {}".format(result["dest"]))
    print("SIOS cards copied: {}".format(result["sios_copied"]))
    if result["sios_missing"]:
        print("SIOS ids missing from source: {}".format(
            ", ".join(result["sios_missing"])
        ))
    print("Synthetic EkoKarty fixtures: {}".format(result["synthetic_ekokarty"]))
    print("Total cards: {}".format(result["total_cards"]))
    volunteer = volunteer_sqlite_path()
    dest = Path(result["dest"]).resolve()
    if dest == volunteer:
        print("ERROR: dest is the volunteer database", file=sys.stderr)
        return 2
    print("Volunteer DB left untouched: {}".format(volunteer))
    print("Project root: {}".format(PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
