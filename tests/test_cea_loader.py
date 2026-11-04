"""Загрузка баз ядра NASA CEA по пути, который ядро может открыть (Windows, русский путь)."""

from pathlib import Path

from astra.core import cea_loader


def test_latin_path_used_as_is(tmp_path):
    cea_file = tmp_path / "cea" / "__init__.py"
    assert cea_loader.data_dir(str(cea_file), "3.3.4", windows=True) == str(cea_file.parent / "data")


def test_non_windows_path_used_as_is(tmp_path):
    cea_file = tmp_path / "Программа" / "cea" / "__init__.py"
    assert cea_loader.data_dir(str(cea_file), "3.3.4", windows=False) == str(cea_file.parent / "data")


def test_ascii_copy_of_databases(tmp_path, monkeypatch):
    src = tmp_path / "Проверка" / "data"
    src.mkdir(parents=True)
    for name in cea_loader.FILES:
        (src / name).write_bytes(b"x" * 10)
    common = tmp_path / "common"
    monkeypatch.setenv("ProgramData", str(common))
    out = Path(cea_loader._ascii_copy(src, "3.3.4"))
    assert out == common / "Astra" / "cea-3.3.4"
    assert all((out / n).read_bytes() == b"x" * 10 for n in cea_loader.FILES)
    # повторный вызов не ломает готовую копию; изменённая база копируется заново
    (src / "thermo.lib").write_bytes(b"y" * 12)
    assert Path(cea_loader._ascii_copy(src, "3.3.4")) == out
    assert (out / "thermo.lib").read_bytes() == b"y" * 12


def test_core_initialized():
    import cea

    from astra.core import session  # noqa: F401  (загружает ядро)

    assert cea.is_initialized()
