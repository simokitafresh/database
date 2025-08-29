import pytest

from app.services.normalize import normalize_symbol


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("brk.b", "BRK-B"),
        ("BRK.B", "BRK-B"),
        ("7203.T", "7203.T"),
    ],
)
def test_normalize_symbol(inp, expected):
    assert normalize_symbol(inp) == expected
