"""Значок программы для exe и установщика: packaging/astra.ico (и astra.png для документации).

Значок рисуется тем же кодом, что и в окне программы (astra.app.space.app_icon_pixmap).
Запуск из корня репозитория:  python tools/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(pm) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(data)


def write_ico(path: Path, images: list[tuple[int, bytes]]) -> None:
    """ICO с PNG внутри (поддерживается Windows Vista и новее)."""
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        s = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    path.write_bytes(head + entries + blobs)


def main() -> int:
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from astra.app.space import app_icon_pixmap
    write_ico(ROOT / "packaging" / "astra.ico", [(s, png_bytes(app_icon_pixmap(s))) for s in SIZES])
    app_icon_pixmap(512).save(str(ROOT / "packaging" / "astra.png"))
    print("packaging/astra.ico, packaging/astra.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
