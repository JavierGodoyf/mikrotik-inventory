import pytest

from app.versions import Version, is_newer, parse


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("7.16.2", Version(7, 16, 2)),
        ("7.16.2 (stable)", Version(7, 16, 2)),
        ("  6.49.23  ", Version(6, 49, 23)),
        ("7.26beta4", Version(7, 26, 0, "beta", 4)),
        ("7.17rc1", Version(7, 17, 0, "rc", 1)),
        ("7.10", Version(7, 10, 0)),
    ],
)
def test_parse(raw, expected):
    assert parse(raw) == expected


def test_parse_invalid():
    assert parse(None) is None
    assert parse("") is None
    assert parse("stable") is None
    assert parse("7") is None


def test_numeric_order_not_lexical():
    assert parse("7.10") > parse("7.9.9")
    assert parse("7.16.2") > parse("7.16.1")


def test_prerelease_is_older_than_release():
    assert parse("7.17rc2") < parse("7.17")
    assert parse("7.17beta3") < parse("7.17rc1")
    assert parse("7.17rc1") > parse("7.16.9")


def test_major_branch():
    assert parse("6.49.23") < parse("7.0")
    assert parse("7.16.2") > parse("6.99.99")


def test_is_newer():
    assert is_newer("7.25", "7.24.1")
    assert not is_newer("7.25", "7.25")
    assert not is_newer("7.25", "7.25.1")
    assert not is_newer(None, "7.25")
    assert not is_newer("7.25", "nonsense")


def test_str_roundtrip():
    assert str(parse("7.16.2")) == "7.16.2"
    assert str(parse("6.49.23")) == "6.49.23"
    assert str(parse("7.26beta4")) == "7.26beta4"
