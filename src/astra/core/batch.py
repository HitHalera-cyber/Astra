"""Пакетный запуск независимых расчётов.

Ядро NASA CEA хранит базу веществ и рабочие массивы в глобальном состоянии
процесса, поэтому параллельные расчёты выполняются в отдельных процессах.
В каждом процессе сеанс (`CeaSession`) для одного набора веществ создаётся
один раз и используется для всех его точек.

Ошибка исходных данных в одной точке не прерывает серию: на её месте в списке
результатов стоит объект `TaskFailure` с русским сообщением.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
import multiprocessing as mp
import os
from typing import Any, Callable, Iterable, Sequence

from .errors import AstraError
from .propellant import ProductOptions, Propellant
from .results import EquilibriumResult, NozzleResult
from .session import CeaSession


@dataclass(frozen=True)
class Task:
    """Одна независимая расчётная точка.

    kind   — "equilibrium" (CeaSession.equilibrium) или "nozzle" (CeaSession.nozzle);
    args   — позиционные аргументы метода (например, ("HP", Ratio.km(6.0)));
    kwargs — именованные аргументы метода (например, {"p": 5e6}).
    """

    kind: str
    propellant: Propellant
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    products: ProductOptions = ProductOptions()

    def __hash__(self) -> int:  # dict в kwargs не хешируется; задача идентифицируется по позиции
        return id(self)


@dataclass(frozen=True)
class TaskFailure:
    index: int
    message: str


Result = EquilibriumResult | NozzleResult | TaskFailure

_SESSIONS: dict[tuple, CeaSession] = {}


def _session(task: Task) -> CeaSession:
    key = (task.propellant, task.products)
    sess = _SESSIONS.get(key)
    if sess is None:
        sess = CeaSession(task.propellant, task.products)
        _SESSIONS[key] = sess
    return sess


def run_task(index: int, task: Task) -> Result:
    try:
        sess = _session(task)
        if task.kind == "equilibrium":
            return sess.equilibrium(*task.args, **task.kwargs)
        if task.kind == "nozzle":
            return sess.nozzle(*task.args, **task.kwargs)
        return TaskFailure(index, f"Неизвестный тип расчёта: {task.kind}.")
    except AstraError as exc:
        return TaskFailure(index, str(exc))


def _run_chunk(chunk: list[tuple[int, Task]]) -> list[Result]:
    return [run_task(i, t) for i, t in chunk]


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def run_batch(tasks: Sequence[Task], workers: int | None = None,
              progress: Callable[[int, int], None] | None = None,
              chunk_size: int | None = None) -> list[Result]:
    """Выполнить задачи и вернуть результаты в исходном порядке.

    workers=1 — последовательно в текущем процессе; None — по числу ядер ЦП − 1.
    progress(done, total) вызывается после каждого завершённого блока задач.
    """
    tasks = list(tasks)
    total = len(tasks)
    if total == 0:
        return []
    workers = default_workers() if workers is None else max(1, int(workers))
    indexed = list(enumerate(tasks))
    if workers == 1 or total == 1:
        out: list[Result] = []
        for i, t in indexed:
            out.append(run_task(i, t))
            if progress:
                progress(i + 1, total)
        return out

    size = chunk_size or max(1, min(64, total // (workers * 4) or 1))
    chunks = [indexed[j:j + size] for j in range(0, total, size)]
    results: list[Result | None] = [None] * total
    done = 0
    ctx = mp.get_context("spawn")  # одинаково на Windows и Linux
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        for chunk, res in zip(chunks, pool.map(_run_chunk, chunks)):
            for (i, _), r in zip(chunk, res):
                results[i] = r
            done += len(chunk)
            if progress:
                progress(done, total)
    return results  # type: ignore[return-value]
