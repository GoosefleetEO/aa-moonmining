from pathlib import Path


def test_data_filename() -> str:
    """Return filename containing eveuniverse testdata."""
    return Path(__file__).parent / "eveuniverse.json"
