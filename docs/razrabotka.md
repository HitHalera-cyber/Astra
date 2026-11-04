# Astra — документация разработчика

## Устройство

```
src/astra/
  core/       адаптер к ядру NASA CEA (пакет cea 3.3.4): единицы СИ, отечественные
              обозначения (notation.py), расчёты (session.py), пакетный запуск в
              процессах (batch.py), сетки значений (grid.py), база веществ (species_db.py)
  projects/   модель проекта и SQLite (model.py, store.py), запуск расчёта (run.py),
              параметрические исследования (study.py), сопло и Iуд (nozzle.py),
              наборы данных для таблиц и графиков (datasets.py), экспорт (export.py)
  app/        интерфейс PySide6: главное окно, 12 разделов (pages/), фоновые потоки
  selftest.py самопроверка установленной программы (--selftest)
```

Правила, которые проверяют тесты:

- физику считает только ядро. В оболочке есть лишь точные соотношения между его
  величинами (α = Kм / Kм⁰, H = i + W²/2, Iуд(Pн) = Iуд.п − Pн·ε·C*/Pк, Kт(Pн) = Iуд(Pн) / C*);
- несошедшиеся точки не заменяются: в таблицах и наборах данных у них NaN и сообщение ядра;
- имена величин ядра не меняются, перевод в отечественные обозначения — только в
  `core/notation.py`.

Особенности ядра, учтённые в адаптере, описаны в [etap-1-audit.md](etap-1-audit.md):
ударная волна требует масс на 1 кмоль смеси; вязкость ядро возвращает в мП, а
теплопроводность в мВт/(см·К); для SP и SV нужна явная энтропия.

## Окружение и тесты

```
python -m pip install -e ".[test]"
QT_QPA_PLATFORM=offscreen python -m pytest        # Linux без экрана; в Windows переменная не нужна
python tools/verify_nasa.py                        # отчёт docs/etap-8-verification.md
python tools/gen_notation.py                       # таблица docs/oboznacheniya.md
```

Python 3.11–3.13. На Python 3.11 нельзя ставить PySide6 6.12.0: эта версия портит счётчик
ссылок None, и программа аварийно завершается. Ограничение записано в `pyproject.toml`,
регрессионный тест лежит в `tests/test_gui.py`.

## Сборка Windows

Сборку выполняет GitHub Actions (`.github/workflows/build-windows.yml`) на Windows, Python 3.13:

1. `pyinstaller packaging/astra.spec` собирает `dist/Astra/Astra.exe` в режиме onedir.
   В сборку входят ядро NASA CEA (расширение, библиотека Fortran, thermo.lib, trans.lib),
   база thermo.inp, русские переводы Qt, лицензии.
2. `dist/Astra/Astra.exe --selftest` проверяет собранную программу: сверку с задачей
   NASA №8, базу веществ, расчёт в двух процессах (запуск дочерних процессов exe) и
   открытие всех разделов. Если самопроверка не пройдена, сборка останавливается.
3. Inno Setup (`packaging/astra.iss`) собирает `dist/installer/Astra-<версия>-setup.exe`.
   Установщик и папка программы сохраняются как артефакты сборки.

Выпуск версии: поменяйте `version` в `pyproject.toml` и `__version__` в
`src/astra/__init__.py` (тест проверяет, что они совпадают), затем создайте метку
`v<версия>`. Сборка по метке прикладывает установщик к выпуску (GitHub Release).

Собрать локально в Windows:

```
python -m pip install -e . pyinstaller
pyinstaller packaging/astra.spec --noconfirm
dist\Astra\Astra.exe --selftest selftest.txt
"C:\Program Files (x86)\Inno Setup 6\iscc.exe" /DAppVersion=1.0.0 packaging\astra.iss
```
