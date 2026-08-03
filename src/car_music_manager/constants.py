"""Constants deliberately kept free of runtime side effects."""

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg"})
WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)
