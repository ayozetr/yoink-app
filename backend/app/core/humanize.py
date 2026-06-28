"""Small OS-independent formatting helpers shared across services."""

from __future__ import annotations


def humanize_bytes(num: float) -> str:
    """Render a byte count as e.g. '3.2 MB' / '182 GB'."""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        # Roll over before rounding would display "1024" (e.g. 1023.6 B → 1.0 KB).
        if round(size, 0 if unit == "B" else 1) < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
