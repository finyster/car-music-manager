"""Application-specific exceptions."""


class CarMusicError(Exception):
    """Base exception for expected command failures."""


class ExternalToolError(CarMusicError):
    """An external executable was unavailable or failed."""


class ValidationError(CarMusicError):
    """A user supplied value or produced media was invalid."""
