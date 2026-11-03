"""Хранилище проектов SQLite."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from astra.core.results import EquilibriumResult, NozzleResult, StatePoint, WaveResult

from .model import CalcRecord, Project

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    created TEXT NOT NULL,
    modified TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    kind TEXT NOT NULL,
    inputs TEXT NOT NULL,
    results TEXT NOT NULL,
    converged INTEGER NOT NULL,
    message TEXT NOT NULL,
    core_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS calculations_project ON calculations(project_id, id);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(v: Any) -> Any:
    """JSON без NaN/inf (не вычисленные величины хранятся как null)."""
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if hasattr(v, "__dataclass_fields__"):
        from dataclasses import asdict
        return _clean(asdict(v))
    return v


def point_to_dict(p: StatePoint) -> dict[str, Any]:
    return {"kind": p.kind, "values": p.values, "mole_fractions": p.mole_fractions,
            "mass_fractions": p.mass_fractions, "regime": p.regime,
            "target": p.target, "case": p.case, "t_target": p.t_target,
            "target_key": p.target_key}


def result_to_dict(r: EquilibriumResult | NozzleResult | WaveResult) -> dict[str, Any]:
    if hasattr(r, "to_dict"):   # сводка серии параметрического исследования
        return r.to_dict()
    if isinstance(r, WaveResult):
        return {"type": r.problem, "points": [point_to_dict(p) for p in r.points], "cases": r.cases,
                "assumptions": r.assumptions, "warnings": r.warnings}
    if isinstance(r, NozzleResult):
        return {"type": "nozzle", "model": r.model, "points": [point_to_dict(p) for p in r.points],
                "assumptions": r.assumptions, "warnings": r.warnings}
    return {"type": "equilibrium", "problem": r.problem, "points": [point_to_dict(r.point)]}


class ProjectStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # --- проекты
    def save(self, project: Project) -> Project:
        data = json.dumps(_clean(project.to_dict()), ensure_ascii=False)
        now = _now()
        if project.id is None:
            cur = self.db.execute("INSERT INTO projects(name, data, created, modified) VALUES (?,?,?,?)",
                                  (project.name, data, now, now))
            project.id, project.created = cur.lastrowid, now
        else:
            self.db.execute("UPDATE projects SET name=?, data=?, modified=? WHERE id=?",
                            (project.name, data, now, project.id))
        project.modified = now
        self.db.commit()
        return project

    def load(self, project_id: int) -> Project:
        row = self.db.execute("SELECT id, data, created, modified FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Проект {project_id} не найден.")
        p = Project.from_dict(json.loads(row[1]))
        p.id, p.created, p.modified = row[0], row[2], row[3]
        return p

    def list(self) -> list[tuple[int, str, str, str]]:
        """(id, имя, создан, изменён), последние изменённые первыми."""
        return list(self.db.execute("SELECT id, name, created, modified FROM projects ORDER BY modified DESC, id DESC"))

    def duplicate(self, project_id: int, new_name: str | None = None) -> Project:
        p = self.load(project_id)
        p.id = None
        p.name = new_name or f"{p.name} (копия)"
        return self.save(p)

    def delete(self, project_id: int) -> None:
        self.db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        self.db.commit()

    # --- журнал расчётов
    def log_calculation(self, project_id: int, kind: str, inputs: dict[str, Any],
                        result: EquilibriumResult | NozzleResult, core_version: str) -> int:
        cur = self.db.execute(
            "INSERT INTO calculations(project_id, timestamp, kind, inputs, results, converged, message, core_version)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (project_id, _now(), kind, json.dumps(_clean(inputs), ensure_ascii=False),
             json.dumps(_clean(result_to_dict(result)), ensure_ascii=False),
             int(result.converged), result.message, core_version))
        self.db.commit()
        return int(cur.lastrowid)

    def calculations(self, project_id: int) -> list[CalcRecord]:
        rows = self.db.execute(
            "SELECT id, project_id, timestamp, kind, inputs, results, converged, message, core_version "
            "FROM calculations WHERE project_id=? ORDER BY id DESC", (project_id,))
        return [CalcRecord(r[0], r[1], r[2], r[3], json.loads(r[4]), json.loads(r[5]), bool(r[6]), r[7], r[8])
                for r in rows]
