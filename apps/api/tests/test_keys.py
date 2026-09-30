import pytest

from app.audio.keys import normalize_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Am", ("Am", "8A")),
        ("A minor", ("Am", "8A")),
        ("C", ("C", "8B")),
        ("C major", ("C", "8B")),
        ("Cmaj", ("C", "8B")),
        ("F#m", ("F#m", "11A")),
        ("Gbm", ("F#m", "11A")),
        ("G#m", ("Abm", "1A")),
        ("Bb", ("Bb", "6B")),
        ("Bbm", ("Bbm", "3A")),
        ("Fm", ("Fm", "4A")),
        ("E", ("E", "12B")),
        ("C#", ("Db", "3B")),
        ("B", ("B", "1B")),
        ("11A", ("F#m", "11A")),
        ("7a", ("Dm", "7A")),
        ("12B", ("E", "12B")),
        ("1m", ("Am", "8A")),
        ("1d", ("C", "8B")),
        ("6m", ("Abm", "1A")),
        (" 4A ", ("Fm", "4A")),
    ],
)
def test_normalize_key(raw, expected):
    assert normalize_key(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "H", "13A", "o", "unknown"])
def test_normalize_key_unknown(raw):
    assert normalize_key(raw) == (None, None)
