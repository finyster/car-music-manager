import sys
from pathlib import Path

import pytest


def test_authorized_link_import_requires_explicit_confirmation() -> None:
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from import_approved_links import import_links

        selection = Path(__file__).parents[1] / "data" / "selection.csv"
        with pytest.raises(ValueError, match="--confirm-authorized"):
            import_links(selection, Path("D:/CarMusic"), confirm_authorized=False)
    finally:
        sys.path.remove(str(scripts))
