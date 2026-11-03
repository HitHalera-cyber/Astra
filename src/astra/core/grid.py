"""Расчётные сетки параметров: фиксированное значение, шаг или число точек."""

from __future__ import annotations

import itertools
import math
from typing import Sequence

import numpy as np

from .errors import InputError


def fixed(value: float) -> np.ndarray:
    return np.array([float(value)])


def by_step(start: float, stop: float, step: float) -> np.ndarray:
    """От start до stop включительно с шагом step (знак шага по направлению)."""
    if step == 0 or math.isnan(step):
        raise InputError("Шаг изменения параметра не может быть равен нулю.")
    span = stop - start
    if span != 0 and (span > 0) != (step > 0):
        raise InputError("Знак шага не соответствует направлению от начального к конечному значению.")
    n = int(math.floor(abs(span) / abs(step) + 1e-9)) + 1
    values = start + step * np.arange(n)
    if abs(values[-1] - stop) > 1e-9 * max(1.0, abs(stop)):
        values = np.append(values, stop)  # конечное значение всегда входит в сетку
    return values


def by_count(start: float, stop: float, count: int, log: bool = False) -> np.ndarray:
    """count точек от start до stop включительно; log=True — логарифмическое распределение."""
    if count < 1:
        raise InputError("Число расчётных точек должно быть не меньше 1.")
    if count == 1:
        return np.array([float(start)])
    if log:
        if start <= 0 or stop <= 0:
            raise InputError("Для логарифмического распределения значения должны быть положительными.")
        return np.geomspace(start, stop, count)
    return np.linspace(start, stop, count)


def product(**axes: Sequence[float]) -> list[dict[str, float]]:
    """Многомерный массив точек: все сочетания значений осей."""
    names = list(axes)
    return [dict(zip(names, combo)) for combo in itertools.product(*(list(map(float, axes[n])) for n in names))]
