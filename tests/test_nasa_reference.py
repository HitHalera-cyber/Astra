"""Сравнение astra.core с эталонными выводами NASA CEA (RP-1311).

Astra вызывает ядро через свой адаптер (единицы СИ, Kм, отечественные ключи);
результаты должны совпадать с выводом оригинальной программы при тех же
исходных данных. Допуск 5e-4 отн. (собственные тесты NASA используют 1e-2);
наибольшее наблюдаемое расхождение — 1,1e-4 по числу Маха в дозвуковом
сечении задачи №8 (эталон получен программой CEA2 2004 г.).
"""

import math

import pytest

from astra.core import (BAR, CeaSession, Component, FUEL, OXIDIZER, ProductOptions, Propellant, Ratio)

import nasa_reference as ref

REL = 5e-4
ATM = 101325.0

STATE_ROWS = {  # строка эталона -> (ключ Astra, множитель СИ -> единица эталона)
    "P, BAR": ("p", 1 / BAR),
    "T, K": ("t", 1.0),
    "H, KJ/KG": ("i", 1e-3),
    "S, KJ/(KG)(K)": ("s", 1e-3),
    "M, (1/n)": ("mu_c", 1.0),
    "Cp, KJ/(KG)(K)": ("cp", 1e-3),
    "GAMMAs": ("k", 1.0),
    "SON VEL,M/SEC": ("a", 1.0),
    "MACH NUMBER": ("M", 1.0),
    "RHO, KG/CU M": ("rho", 1.0),
}
PERF_ROWS = {
    "Ae/At": ("eps", 1.0),
    "CSTAR, M/SEC": ("c_star", 1.0),
    "CF": ("kt", 1.0),
    "Ivac, M/SEC": ("isp_vac", 1.0),
    "Isp, M/SEC": ("isp", 1.0),
}


def close(a, b, rel=REL, abs_=1e-9):
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)


def compare_block(block, points, match=("P, BAR", "p", 1 / BAR)):
    """Каждый столбец эталона сопоставляется с точкой Astra по величине match (по умолчанию P)."""
    label_m, key_m, scale_m = match
    checked = 0
    for col in range(block.ncols):
        ref_m = block.value(label_m, col)
        pt = min(points, key=lambda x: abs(x[key_m] * scale_m - ref_m))
        assert close(pt[key_m] * scale_m, ref_m), f"нет точки Astra с {label_m} = {ref_m}"
        for label, (key, scale) in STATE_ROWS.items():
            if label in block.rows:
                expected = block.value(label, col)
                assert close(pt[key] * scale, expected, abs_=1e-6), f"{label} в столбце {col}: {pt[key] * scale} != {expected}"
                checked += 1
        if col == 0 or pt.kind in ("injector", "chamber_inf", "chamber_end"):
            continue  # характеристики сопла сравниваются начиная с критического сечения
        for label, (key, scale) in PERF_ROWS.items():
            if label in block.rows:
                expected = block.value(label, col)
                assert close(pt[key] * scale, expected), f"{label} в столбце {col}: {pt[key] * scale} != {expected}"
                checked += 1
    return checked


def test_example8_rocket_equilibrium():
    prop = Propellant((Component("H2(L)", FUEL, t0=20.27), Component("O2(L)", OXIDIZER, t0=90.17)))
    res = CeaSession(prop).nozzle(Ratio.km(5.55157), 53.3172 * BAR, pk_p=[10, 100, 1000],
                                  eps_sub=[1.58], eps=[25, 50, 75])
    assert res.converged, res.message
    blocks = ref.parse("example8")
    assert len(blocks) == 2
    assert sum(compare_block(b, res.points) for b in blocks) > 100


def test_example12_rocket_frozen_at_throat():
    only = ("CO CO2 H HNO HNO2 HO2 H2 H2O H2O2 N NO NO2 N2 N2O O OH O2 HCO NH CH4 NH2 NH3 H2O(L) C(gr)").split()
    prop = Propellant((Component("CH6N2(L)", FUEL), Component("N2O4(L)", OXIDIZER)))
    sess = CeaSession(prop, ProductOptions(only=tuple(only)))
    blocks = [b for b in ref.parse("example12") if b.frozen]
    pk = blocks[0].value("P, BAR", 0) * BAR  # 1000 psia в пересчёте исходной программы
    res = sess.nozzle(Ratio.km(2.5), pk, pk_p=[68.0457], eps=[5, 10, 25, 50, 75, 100, 150, 200],
                      model="frozen", freeze_at="throat")
    assert res.converged, res.message
    assert len(blocks) == 2
    assert sum(compare_block(b, res.points) for b in blocks) > 100


def test_example3_hp_multicomponent():
    prop = Propellant((
        Component("Air", OXIDIZER, amount=1.0, t0=700.0),
        Component("C7H8(L)", FUEL, amount=0.4, t0=298.15),
        Component("C8H18(L),n-octa", FUEL, amount=0.6, t0=298.15),
    ))
    sess = CeaSession(prop, ProductOptions(omit=tuple(ref.omit_list("example3")), trace=1e-15))
    block = ref.parse("example3")[0]
    points = []
    for p_bar in (100.0, 10.0, 1.0):
        r = sess.equilibrium("HP", Ratio.km(17.0), p=p_bar * BAR)
        assert r.converged, r.message
        points.append(r.point)
    assert compare_block(block, points) >= 3 * 7


def test_example14_tp_with_condensation():
    # 100 моль H2(L) и 60 моль O2(L): массовое соотношение по молярным массам базы NASA
    km = 60 * 31.9988 / (100 * 2.01588)
    prop = Propellant((Component("H2(L)", FUEL, t0=20.27), Component("O2(L)", OXIDIZER, t0=90.17)))
    sess = CeaSession(prop)
    block = ref.parse("example14")[0]
    points = []
    for col in range(block.ncols):
        t = block.value("T, K", col)
        r = sess.equilibrium("TP", Ratio.km(km), p=0.05 * ATM, t=t)
        assert r.converged, r.message
        points.append(r.point)
    assert compare_block(block, points, match=("T, K", "t", 1.0)) >= block.ncols * 6
    # при 300 К вода конденсируется — проверяем, что конденсат присутствует в составе
    cold = points[-1]
    assert cold.mole_fractions.get("H2O(L)", 0.0) + cold.mole_fractions.get("H2O(cr)", 0.0) > 0.1
