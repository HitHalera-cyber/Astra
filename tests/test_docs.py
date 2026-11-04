"""Документация и версия согласованы с кодом."""

from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_notation_doc_is_up_to_date():
    import gen_notation
    assert (ROOT / "docs" / "oboznacheniya.md").read_text(encoding="utf-8") == gen_notation.render(), \
        "docs/oboznacheniya.md устарел: запустите python tools/gen_notation.py"


def test_version_matches_pyproject():
    import astra
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["version"] == astra.__version__


def test_installer_ships_existing_files():
    raw = (ROOT / "packaging" / "astra.iss").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "Inno Setup читает UTF-8 только с BOM"
    iss = raw.decode("utf-8-sig")
    for line in iss.splitlines():
        if line.startswith("Source:") and "dist\\" not in line:
            rel = line.split('"')[1].replace("..\\", "").replace("\\", "/")
            assert (ROOT / rel).exists(), rel
    assert (ROOT / "NOTICE.md").exists()


def test_selftest_passes():
    from astra.selftest import run
    ok, lines = run()
    assert ok, "\n".join(lines)


def test_docs_build(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("markdown")
    import build_docs
    monkeypatch.setattr(build_docs, "OUT", tmp_path)
    made = {p.name for p in build_docs.build()}
    assert {"rukovodstvo.html", "oboznacheniya.html", "NOTICE.txt"} <= made
    html = (tmp_path / "rukovodstvo.html").read_text(encoding="utf-8")
    assert 'href="oboznacheniya.html"' in html and 'href="oboznacheniya.md"' not in html
    assert (tmp_path / "NOTICE.txt").read_bytes().startswith(b"\xef\xbb\xbf")
