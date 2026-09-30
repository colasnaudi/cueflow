"""Musical key normalisation: any common notation -> (musical_key, camelot_key)."""

import re

# Index i holds Camelot number i + 1.
MINOR_KEYS = ["Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "Dbm"]
MAJOR_KEYS = ["B", "F#", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E"]

NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])\s*([AB])$", re.IGNORECASE)
OPEN_KEY_RE = re.compile(r"^(1[0-2]|[1-9])\s*([MD])$", re.IGNORECASE)
NOTE_RE = re.compile(
    r"^([A-G])\s*([#♯b♭]?)\s*(m|min|minor|moll|maj|major|dur)?$",
    re.IGNORECASE,
)


def _pc(root: str) -> int:
    base, accidental = root[0].upper(), root[1:]
    pc = NOTE_PC[base]
    if accidental in ("#", "♯"):
        pc += 1
    elif accidental in ("b", "♭"):
        pc -= 1
    return pc % 12


def _camelot_number(pc: int, minor: bool) -> int:
    major_pc = (pc + 3) % 12 if minor else pc
    return (major_pc * 7 + 7) % 12 + 1


def normalize_key(raw: str | None) -> tuple[str | None, str | None]:
    """Return (musical_key, camelot_key), e.g. "A minor" -> ("Am", "8A"). Unknown -> (None, None)."""
    if not raw:
        return None, None
    value = raw.strip().replace("♯", "#").replace("♭", "b")
    if not value:
        return None, None

    if match := CAMELOT_RE.match(value):
        number, letter = int(match.group(1)), match.group(2).upper()
    elif match := OPEN_KEY_RE.match(value):
        number = (int(match.group(1)) + 6) % 12 + 1
        letter = "A" if match.group(2).upper() == "M" else "B"
    elif match := NOTE_RE.match(value):
        root, accidental, mode = match.group(1), match.group(2).lower(), match.group(3) or ""
        # A bare uppercase "M" is the major shorthand (e.g. "CM"); lowercase "m" is minor.
        minor = mode == "m" or mode.lower() in ("min", "minor", "moll")
        number = _camelot_number(_pc(root.upper() + accidental), minor)
        letter = "A" if minor else "B"
    else:
        return None, None

    musical = (MINOR_KEYS if letter == "A" else MAJOR_KEYS)[number - 1]
    return musical, f"{number}{letter}"
