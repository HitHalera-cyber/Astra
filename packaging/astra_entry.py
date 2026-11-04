"""Точка входа собранной программы (PyInstaller)."""

import multiprocessing
import sys

if __name__ == "__main__":
    # дочерние процессы пакетных серий запускаются тем же exe: freeze_support
    # передаёт им управление, и окно программы в них не открывается
    multiprocessing.freeze_support()
    from astra.app.main import main
    sys.exit(main())
