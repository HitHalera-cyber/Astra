"""Экспорт наборов данных: CSV, XLSX и отчёт (HTML; PDF строит интерфейс через Qt).

Числа записываются в единицах отображения (МПа, кДж/кг, …), как в таблицах
программы; NaN — как пустая ячейка. В каждом файле указаны версия ядра NASA CEA,
дата и происхождение результатов.
"""

from __future__ import annotations

import csv
from datetime import datetime
import html
import math
from pathlib import Path
from typing import Any, Iterable

from astra.core import core_version

from .datasets import NUMBER, Dataset

ORIGIN = ("Результаты получены оригинальным вычислительным ядром NASA CEA (Chemical Equilibrium with "
          "Applications, NASA Glenn Research Center; пакет cea, лицензия Apache-2.0) через программу Astra.")


def provenance(project_name: str | None = None) -> dict[str, str]:
    d = {"Программа": "Astra", "Ядро": f"NASA CEA {core_version()}",
         "Дата": datetime.now().strftime("%d.%m.%Y %H:%M")}
    if project_name:
        d["Проект"] = project_name
    return d


def _cell(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _num_text(value: Any, decimal: str) -> str:
    v = _cell(value)
    if v is None:
        return ""
    if isinstance(v, float):
        s = f"{v:.10g}"
        return s.replace(".", decimal)
    return str(v)


def to_csv(ds: Dataset, path: str | Path, *, sep: str = ";", decimal: str = ",",
           columns: Iterable[str] | None = None, rows: Iterable[int] | None = None) -> Path:
    """CSV для русского Excel: разделитель «;», десятичная запятая, UTF-8 с BOM."""
    path = Path(path)
    keys = list(columns) if columns is not None else [c.key for c in ds.columns]
    idx = [ds.index(k) for k in keys]
    sel = list(rows) if rows is not None else range(len(ds.rows))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=sep)
        w.writerow([ds.columns[i].label for i in idx])
        for r in sel:
            row = ds.rows[r]
            w.writerow([_num_text(ds.columns[i].display(row[i]), decimal) if ds.columns[i].kind == NUMBER
                        else row[i] for i in idx])
    return path


def to_xlsx(datasets: list[Dataset], path: str | Path, *, project_name: str | None = None,
            selections: dict[str, tuple[list[str] | None, list[int] | None]] | None = None) -> Path:
    """Книга Excel: лист «Сведения» и по листу на набор данных (числа — числами)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    path = Path(path)
    wb = Workbook()
    info = wb.active
    info.title = "Сведения"
    info.append(["Astra — результаты расчёта"])
    info["A1"].font = Font(bold=True, size=13)
    for k, v in provenance(project_name).items():
        info.append([k, v])
    info.append([])
    info.append([ORIGIN])
    info.append(["Несошедшиеся точки не заменяются: их значения оставлены пустыми, причина — в столбце «Сходимость»."])
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 40
    used: set[str] = set()
    for ds in datasets:
        title = _sheet_title(ds.name, used)
        ws = wb.create_sheet(title)
        cols, rows = (selections or {}).get(ds.name, (None, None))
        keys = cols if cols is not None else [c.key for c in ds.columns]
        idx = [ds.index(k) for k in keys]
        for k, v in ds.meta.items():
            ws.append([k, v])
        if ds.meta:
            ws.append([])
        header_row = ws.max_row + 1 if ds.meta else 1
        ws.append([ds.columns[i].label for i in idx])
        for c in ws[header_row]:
            c.font = Font(bold=True)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        sel = rows if rows is not None else range(len(ds.rows))
        for r in sel:
            row = ds.rows[r]
            ws.append([_cell(ds.columns[i].display(row[i])) for i in idx])
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
        for j, i in enumerate(idx, start=1):
            ws.column_dimensions[get_column_letter(j)].width = max(10, min(40, len(ds.columns[i].label) + 4))
    wb.save(path)
    return path


def _sheet_title(name: str, used: set[str]) -> str:
    base = "".join(ch for ch in name if ch not in "[]:*?/\\")[:28] or "Данные"
    title, n = base, 2
    while title in used:
        title = f"{base[:25]} {n}"
        n += 1
    used.add(title)
    return title


def _fmt(value: Any, kind: str) -> str:
    if kind != NUMBER:
        return html.escape("" if value is None else str(value))
    v = _cell(value)
    if v is None:
        return "—"
    return (f"{v:.6g}" if v == 0 or 1e-3 <= abs(v) < 1e7 else f"{v:.5e}").replace(".", ",")


def report_html(title: str, sections: list[tuple[str, Any]], *, project_name: str | None = None,
                inputs: dict[str, str] | None = None) -> str:
    """Отчёт в HTML. sections: (заголовок, Dataset | str HTML | ("image", ссылка на PNG, ширина))."""
    css = ("body{font-family:'Segoe UI',Arial,sans-serif;font-size:9pt;color:#1c2127}"
           "h1{font-size:15pt;margin:0 0 4px 0}h2{font-size:11pt;margin:14px 0 4px 0}"
           "table{border-collapse:collapse;margin:4px 0}td,th{border:1px solid #b9c0c8;padding:2px 5px}"
           "th{background:#e9ecf0;font-weight:600}td.n{text-align:right}.muted{color:#5f6873}.bad{color:#c3332b}")
    out = [f"<html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style></head><body>",
           f"<h1>{html.escape(title)}</h1>"]
    prov = provenance(project_name)
    out.append("<p class='muted'>" + " · ".join(f"{html.escape(k)}: {html.escape(v)}" for k, v in prov.items())
               + "</p>")
    if inputs:
        out.append("<h2>Исходные данные</h2><table>")
        out += [f"<tr><th align='left'>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in inputs.items()]
        out.append("</table>")
    for head, body in sections:
        out.append(f"<h2>{html.escape(head)}</h2>")
        if isinstance(body, Dataset):
            out.append(_table_html(body))
        elif isinstance(body, tuple) and body and body[0] == "image":
            out.append(f"<img src='{html.escape(body[1])}' width='{body[2] if len(body) > 2 else 640}'>")
        else:
            out.append(str(body))
    out.append(f"<p class='muted'>{html.escape(ORIGIN)}</p></body></html>")
    return "\n".join(out)


def _table_html(ds: Dataset) -> str:
    rows = ["<table><tr>" + "".join(f"<th>{html.escape(c.label)}</th>" for c in ds.columns) + "</tr>"]
    status = ds.index("status") if "status" in [c.key for c in ds.columns] else None
    for r in ds.rows:
        bad = status is not None and str(r[status]).startswith("нет")
        cells = "".join(
            f"<td class='{'n' if c.kind == NUMBER else ''}{' bad' if bad else ''}'>{_fmt(c.display(v), c.kind)}</td>"
            for c, v in zip(ds.columns, r))
        rows.append(f"<tr>{cells}</tr>")
    rows.append("</table>")
    return "\n".join(rows)


def transpose(ds: Dataset, label_key: str = "point") -> Dataset:
    """Таблица «величина × точка» (как в выдаче NASA CEA) для отчёта по одному расчёту."""
    from .datasets import Column, TEXT
    li = ds.index(label_key)
    labels = [str(r[li]) for r in ds.rows]
    cols = [Column("quantity", "Величина", TEXT)] + [Column(f"c{n}", lab, TEXT) for n, lab in enumerate(labels)]
    rows = []
    for j, c in enumerate(ds.columns):
        if j == li:
            continue
        rows.append([c.label] + [_fmt(c.display(r[j]), c.kind) for r in ds.rows])
    return Dataset(ds.name, cols, rows, ds.meta)


def project_inputs(project) -> dict[str, str]:
    """Исходные данные проекта для отчёта (в единицах отображения)."""
    from astra.core import q
    from astra.core.notation import EQUILIBRIUM_PROBLEMS, WAVE_PROBLEMS
    c = project.conditions
    roles = {"fuel": "горючее", "oxidizer": "окислитель", "mixture": "компонент смеси"}
    basis = "массовые" if c.basis == "mass" else "мольные"
    out = {"Компоненты": "; ".join(f"{x.name} ({roles.get(x.role, x.role)}, доля {x.amount:g}, T = {x.t0:g} К)"
                                   for x in project.components) or "не заданы",
           "Доли компонентов": basis}
    calc = ("Камера сгорания и сопло" if c.calc == "rocket" else
            WAVE_PROBLEMS.get(c.calc) or EQUILIBRIUM_PROBLEMS.get(c.calc, c.calc))
    out["Постановка"] = calc
    is_mix = bool(project.components) and all(x.role == "mixture" for x in project.components)
    if not is_mix:
        out[q(c.ratio_kind).symbol] = f"{c.ratio_value:g}"
    if c.calc == "rocket":
        out["Pк"] = f"{c.pk * 1e-6:g} МПа"
        if c.chamber_by_tk:
            out["Tк"] = f"{c.t:g} К"
        out["ε"] = "; ".join(f"{e:g}" for e in c.eps) or "—"
        if c.pk_p:
            out["Pк/P"] = "; ".join(f"{e:g}" for e in c.pk_p)
        out["Модель течения"] = {"equilibrium": "равновесная", "frozen": "замороженная"}[c.model]
        if c.pn is not None:
            out["Pн"] = f"{c.pn * 1e-6:g} МПа"
    elif c.calc in ("shock", "detonation"):
        out["T₁"] = "; ".join(f"{t:g}" for t in c.t1) + " К"
        out["P₁"] = "; ".join(f"{p * 1e-6:g}" for p in c.p1) + " МПа"
        if c.calc == "shock":
            vals = c.u1 if c.shock_by == "u1" else c.mach1
            out["W₁" if c.shock_by == "u1" else "M₁"] = "; ".join(f"{v:g}" for v in vals)
    else:
        if c.calc[1] == "P":
            out["P"] = f"{c.pk * 1e-6:g} МПа"
        else:
            out["v"] = f"{c.v:g} м³/кг"
        if c.calc[0] == "T":
            out["T"] = f"{c.t:g} К"
    if c.ions:
        out["Ионы"] = "учитываются"
    return out
