import multiprocessing
import sys

from astra.app.main import main

if __name__ == "__main__":
    # Пакетные серии считаются в дочерних процессах (spawn): без этой проверки каждый
    # дочерний процесс снова запускал бы окно программы; freeze_support нужен для exe.
    multiprocessing.freeze_support()
    sys.exit(main())
