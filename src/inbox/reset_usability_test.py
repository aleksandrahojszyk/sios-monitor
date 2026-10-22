from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .usability import (
    DEFAULT_USABILITY_SQLITE,
    UsabilitySafetyError,
    normalize_participant_id,
    reset_usability_reviews,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reset usability-test review statuses to NEW. "
            "Does not touch collector cards or the volunteer database. "
            "Preserves participant event logs."
        )
    )
    parser.add_argument(
        "--participant",
        required=True,
        help="Participant identifier for the next session, e.g. P01",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=DEFAULT_USABILITY_SQLITE,
        help="Isolated usability SQLite (default: data/usability/inbox.sqlite)",
    )
    args = parser.parse_args(argv)
    try:
        participant = normalize_participant_id(args.participant)
        result = reset_usability_reviews(args.sqlite, participant)
    except (UsabilitySafetyError, FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Usability reviews reset for next participant {}".format(participant))
    print("SQLite: {}".format(result["sqlite_path"]))
    print("Reviews deleted: {}".format(result["reviews_deleted"]))
    print("Sessions closed: {}".format(result["sessions_finished"]))
    print("Cards preserved: {}".format(result["cards_preserved"]))
    print("Events preserved: {}".format(result["events_preserved"]))
    print(
        "Start the next session with "
        "USABILITY_TEST_MODE=1 PARTICIPANT_ID={}".format(participant)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
