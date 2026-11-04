"""Документы для установщика: руководство и справка в HTML, уведомления — в UTF-8 с BOM.

Запуск: python tools/build_docs.py (нужен пакет markdown). Результат — dist/docs.
Ссылки между документами (*.md) переписываются на *.html, изображения копируются.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "docs"
DOCS = ["rukovodstvo.md", "oboznacheniya.md", "etap-8-verification.md"]
CSS = ("body{font-family:'Segoe UI',Arial,sans-serif;max-width:60em;margin:2em auto;padding:0 1em;"
       "line-height:1.5;color:#1c2127}table{border-collapse:collapse}td,th{border:1px solid #c8ced6;"
       "padding:3px 6px;vertical-align:top}th{background:#eef0f3}code{background:#eef0f3;padding:0 3px}")


def build() -> list[Path]:
    import markdown
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for name in DOCS:
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        text = re.sub(r"\]\(([\w.-]+)\.md\)", r"](\1.html)", text)
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])
        title = text.splitlines()[0].lstrip("# ").strip()
        html = (f"<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>{title}</title>"
                f"<style>{CSS}</style></head><body>{body}</body></html>")
        path = OUT / name.replace(".md", ".html")
        path.write_text(html, encoding="utf-8")
        made.append(path)
    # Inno Setup показывает текстовые файлы в UTF-8 только с BOM
    notice = OUT / "NOTICE.txt"
    notice.write_text((ROOT / "NOTICE.md").read_text(encoding="utf-8"), encoding="utf-8-sig")
    made.append(notice)
    if (ROOT / "docs" / "img").exists():
        shutil.copytree(ROOT / "docs" / "img", OUT / "img", dirs_exist_ok=True)
    return made


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for p in build():
        print(p)
