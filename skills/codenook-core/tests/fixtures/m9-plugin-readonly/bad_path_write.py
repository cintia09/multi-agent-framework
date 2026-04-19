"""Fixture: Path.write_text targeting plugins/ (TC-M9.7-02 variant)."""
from pathlib import Path

def write_bad():
    Path("plugins/sub/bar.yaml").write_text("nope")
