from __future__ import annotations

from typing import Optional, Tuple

from src.sios.models import SOURCE_SYSTEM_SIOS


def parse_location(
    source_system: str, location: Optional[str]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Split SIOS 'województwo / powiat / gmina' location. Leave EkoKarty unstructured."""
    if not location or source_system != SOURCE_SYSTEM_SIOS:
        return None, None, None
    parts = [part.strip() for part in location.split("/") if part.strip()]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 1:
        return parts[0], None, None
    return None, None, None
