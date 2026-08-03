"""Portable paths for a user-owned external music library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LibraryLayout:
    """The fixed directory layout used when ``--library-root`` is supplied."""

    root: Path
    inbox: Path
    originals: Path
    car_ready: Path
    reports: Path
    temp: Path

    @classmethod
    def from_root(cls, root: Path) -> LibraryLayout:
        root = root.expanduser()
        return cls(
            root=root,
            inbox=root / "inbox",
            originals=root / "originals",
            car_ready=root / "car-ready",
            reports=root / "reports",
            temp=root / "temp",
        )

    def ensure(self) -> LibraryLayout:
        """Create all user-owned library folders without touching source files."""
        for path in (self.inbox, self.originals, self.car_ready, self.reports, self.temp):
            path.mkdir(parents=True, exist_ok=True)
        return self
