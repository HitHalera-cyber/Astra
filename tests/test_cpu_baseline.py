"""Astra должна запускаться на старых процессорах x86-64 (AMD Phenom II, Intel Core 2).

NumPy 2.4+ требует x86-64-v2 (SSSE3, SSE4.1, SSE4.2, POPCNT); на AMD Phenom II такой NumPy
в собранной программе падает при загрузке. Базовый набор команд NumPy не должен выходить
за SSE3.
"""

import platform

import pytest

OLD_CPU = {"SSE", "SSE2", "SSE3"}


@pytest.mark.skipif(platform.machine().lower() not in ("x86_64", "amd64"), reason="только x86-64")
def test_numpy_runs_on_sse3_cpu():
    from numpy._core import _multiarray_umath as m

    baseline = set(m.__cpu_baseline__)
    assert baseline <= OLD_CPU, f"NumPy требует команды {sorted(baseline - OLD_CPU)}"
