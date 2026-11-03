"""The accent colours an app can pick. Each is dark enough for white on it."""

COLORS: dict[str, str] = {
    "red": "oklch(0.6 0.22 32)",
    "orange": "oklch(0.64 0.18 52)",
    "green": "oklch(0.58 0.16 150)",
    "teal": "oklch(0.58 0.11 200)",
    "blue": "oklch(0.55 0.19 262)",
    "violet": "oklch(0.55 0.21 300)",
    "pink": "oklch(0.6 0.22 355)",
}
DEFAULT = "red"


def accent(color: str) -> str:
    return COLORS.get(color, COLORS[DEFAULT])
