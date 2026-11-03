"""Пакетный запуск независимых расчётов.

Ядро NASA CEA хранит базу веществ и рабочие массивы в глобальном состоянии
процесса, поэтому параллельные расчёты выполняются в отдельных процессах.
В каждом процессе сеанс (`CeaSession`) для одного набора веществ создаётся
один раз и используется для всех его точек.

Ошибка исходных данных в одной точке не прерывает серию: на её месте в списке
результатов стоит объект `TaskFailure` с русским сообщением.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
import multiprocessing as mp
import os
from typing import Any, Callable, Iterable, Sequence

from .errors import AstraError
from .propellant import ProductOptions, Propellant
from .results import EquilibriumResult, NozzleResult, WaveResult
from .session import CeaSession


@dataclass(frozen=True)
class Task:
    """Одна независимая расчётная точка.

    kind   — метод CeaSession: "equilibrium", "nozzle", "shock" или "detonation";
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


Result = EquilibriumResult | NozzleResult | WaveResult | TaskFailure

KINDS = ("equilibrium", "nozzle", "shock", "detonation")
CANCELLED = "Расчёт точки отменён пользователем."

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
        if task.kind not in KINDS:
            return TaskFailure(index, f"Неизвестный тип расчёта: {task.kind}.")
        sess = _session(task)
        return getattr(sess, task.kind)(*task.args, **task.kwargs)
    except AstraError as exc:
        return TaskFailure(index, str(exc))


def _run_chunk(chunk: list[tuple[int, Task]]) -> list[Result]:
    return [run_task(i, t) for i, t in chunk]


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def run_batch(tasks: Sequence[Task], workers: int | None = None,
              progress: Callable[[int, int], None] | None = None,
              chunk_size: int | None = None,
              cancelled: Callable[[], bool] | None = None) -> list[Result]:
    """Выполнить задачи и вернуть результаты в исходном порядке.

    workers=1 — последовательно в текущем процессе; None — по числу ядер ЦП − 1.
    progress(done, total) вызывается после каждого завершённого блока задач.
    cancelled() проверяется между блоками; после отмены невыполненные точки
    возвращаются как TaskFailure с сообщением об отмене.
    """
    tasks = list(tasks)
    total = len(tasks)
    if total == 0:
        return []
    stop = cancelled or (lambda: False)
    workers = default_workers() if workers is None else max(1, int(workers))
    indexed = list(enumerate(tasks))
    if workers == 1 or total == 1:
        out: list[Result] = []
        for i, t in indexed:
            out.append(TaskFailure(i, CANCELLED) if stop() else run_task(i, t))
            if progress:
                progress(i + 1, total)
        return out

    size = chunk_size or max(1, min(64, total // (workers * 4) or 1))
    chunks = [indexed[j:j + size] for j in range(0, total, size)]
    results: list[Result | None] = [None] * total
    done = 0
    ctx = mp.get_context("spawn")  # одинаково на Windows и Linux
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        pending = {pool.submit(_run_chunk, ch): ch for ch in chunks}
        while pending:
            finished, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for fut in finished:
                chunk = pending.pop(fut)
                if fut.cancelled():
                    res = [TaskFailure(i, CANCELLED) for i, _ in chunk]
                else:
                    res = fut.result()
                for (i, _), r in zip(chunk, res):
                    results[i] = r
                done += len(chunk)
                if progress:
                    progress(done, total)
            if stop():
                for fut in list(pending):
                    if fut.cancel():
                        chunk = pending.pop(fut)
                        for i, _ in chunk:
                            results[i] = TaskFailure(i, CANCELLED)
                        done += len(chunk)
                if progress:
                    progress(done, total)
    return results  # type: ignore[return-value]
