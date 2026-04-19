"""Fixture: legitimate write into memory/ — must NOT be flagged."""
from pathlib import Path

def write_ok():
    open(".codenook/memory/knowledge/x.md", "w").write("ok")
    Path(".codenook/memory/skills/y/SKILL.md").write_text("ok")
