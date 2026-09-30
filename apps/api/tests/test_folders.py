from pathlib import Path

import pytest

from app.services.folders import build_tree, folder_genre, folder_label, is_sample_folder
from app.services.scanner import scan
from tests.conftest import make_mp3

ROOT = Path("/music")


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("02_GENRES/HOUSE/TECH_HOUSE/a.mp3", "Tech House"),
        ("02_GENRES/HOUSE/UK_HOUSE/a.mp3", "UK House"),
        ("02_GENRES/OPEN_FORMAT/RAP:HIP_HOP/a.mp3", "Rap/Hip Hop"),
        ("02_GENRES/LATIN/a.mp3", "Latin"),
        ("Genres/Deep House/a.mp3", "Deep House"),
        ("02_GENRES/TOOLS/VOCALS/Old school vox/a.wav", None),
        ("02_GENRES/a.mp3", None),
        ("Afro House/a.mp3", None),
        ("a.mp3", None),
    ],
)
def test_folder_genre(relative, expected):
    assert folder_genre(ROOT / relative, ROOT) == expected


def test_folder_label_and_sample_folders():
    assert folder_label("01_NEW_MUSIC") == "New Music"
    assert is_sample_folder("02_GENRES/TOOLS/VOCALS")
    assert not is_sample_folder("02_GENRES/HOUSE/TECH_HOUSE")


def test_build_tree_counts_recursively():
    files = [(str(ROOT / p), None) for p in ["A/x.mp3", "A/B/y.mp3", "A/B/z.mp3", "C/w.mp3", "root.mp3"]]
    assert build_tree(files, ROOT) == [
        {
            "name": "A",
            "path": "A",
            "count": 3,
            "children": [{"name": "B", "path": "A/B", "count": 2, "children": []}],
        },
        {"name": "C", "path": "C", "count": 1, "children": []},
    ]


def test_folder_endpoint_and_filter(client, library):
    make_mp3(library / "House_50%" / "c.mp3", title="Percent")
    scan(library)
    tree = client.get("/library/folders").json()
    assert [(n["name"], n["count"]) for n in tree] == [("House", 2), ("House_50%", 1)]

    def titles(folder):
        items = client.get("/tracks", params={"folder": folder}).json()["items"]
        return sorted(t["title"] for t in items)

    assert titles("House") == ["For Your Head", "Jetsetter"]
    # LIKE wildcards in folder names must be escaped: "House_50%" must not match "House".
    assert titles("House_50%") == ["Percent"]


def test_build_tree_counts_each_hash_once_per_folder():
    files = [(str(ROOT / "A/x.mp3"), "h1"), (str(ROOT / "A/B/x.mp3"), "h1"), (str(ROOT / "C/x.mp3"), "h1")]
    assert [(n["name"], n["count"]) for n in build_tree(files, ROOT)] == [("A", 1), ("C", 1)]


def test_dedupe_in_folder_keeps_that_folders_copies(client, library):
    """Regression: the global first copy lived elsewhere, so the folder view looked almost empty."""
    import shutil

    (library / "02_GENRES").mkdir()
    shutil.copy(library / "House" / "a.mp3", library / "02_GENRES" / "a.mp3")
    scan(library)

    def total(**params):
        return client.get("/tracks", params={"dedupe": True, **params}).json()["total"]

    assert total(folder="House") == 2
    assert total(folder="02_GENRES") == 1
    # Globally the numbered-folder copy wins.
    ids = [
        t["path"] for t in client.get("/tracks", params={"dedupe": True, "q": "jetsetter"}).json()["items"]
    ]
    assert len(ids) == 1 and "/02_GENRES/" in ids[0]
    tree = {n["name"]: n["count"] for n in client.get("/library/folders", params={"dedupe": True}).json()}
    assert tree == {"02_GENRES": 1, "House": 2}
