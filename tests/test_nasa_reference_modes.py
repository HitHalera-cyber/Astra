"""Все постановки ядра NASA CEA через astra.core в сравнении с эталонами RP-1311.

Примеры 1, 2, 4, 6, 7, 9, 10, 11, 13 из каталога test/main_interface репозитория
NASA CEA (см. tests/reference/nasa_cea/README.md). Соотношение компонентов
берётся из строки «O/F=» эталона, давление в камере для задач в psia — из
столбца камеры эталона (как в задаче №12), чтобы не вносить погрешность
пересчёта единиц исходной программы.
"""

import math

import pytest

from astra.core import (BAR, CeaSession, Component, FUEL, MIXTURE, OXIDIZER, ProductOptions, Propellant,
                        Ratio)
from astra.core.session import R_UNIV

import nasa_reference as ref
from test_nasa_reference import REL, STATE_ROWS, close, compare_block

ATM = 101325.0
MMHG = ATM / 760.0

TRANSPORT_ROWS = {  # подпись -> (ключ Astra, раздел эталона, множитель СИ -> единица эталона)
    "VISC,MILLIPOISE": ("eta", None, 1e4),
    "CONDUCTIVITY": ("lam", "WITH EQUILIBRIUM REACTIONS", 1.0),
    "PRANDTL NUMBER": ("pr", "WITH EQUILIBRIUM REACTIONS", 1.0),
}
TRANSPORT_FROZEN = {
    "CONDUCTIVITY": ("lam_fr", "WITH FROZEN REACTIONS", 1.0),
    "PRANDTL NUMBER": ("pr_fr", "WITH FROZEN REACTIONS", 1.0),
}


def compare_columns(rows: dict[str, list[float]], points, table: dict, rel=REL, abs_=1e-6) -> int:
    """Столбцы эталона по порядку сопоставляются с точками Astra по порядку."""
    checked = 0
    for label, (key, scale) in table.items():
        if label not in rows:
            continue
        vals = rows[label]
        assert len(vals) == len(points), label
        for col, (pt, expected) in enumerate(zip(points, vals)):
            got = pt[key] * scale
            assert close(got, expected, rel=rel, abs_=abs_), f"{label}, столбец {col}: {got} != {expected}"
            checked += 1
    return checked


def compare_transport(block, points, frozen=True) -> int:
    checked = 0
    tables = [TRANSPORT_ROWS] + ([TRANSPORT_FROZEN] if frozen else [])
    for table in tables:
        for label, (key, section, scale) in table.items():
            rows = block.sections[section] if section else block.rows
            vals = rows[label]
            for col, (pt, expected) in enumerate(zip(points, vals)):
                got = pt[key] * scale
                assert close(got, expected, rel=REL), f"{label} ({section}), столбец {col}: {got} != {expected}"
                checked += 1
    return checked


def air_h2():
    return Propellant((Component("H2", FUEL, 1.0), Component("Air", OXIDIZER, 1.0)), basis="mole")


def test_example1_tp_assigned_t_and_p():
    """TP: H2/воздух, r = 1 и 1,5, P = 1; 0,1; 0,01 атм, T = 3000 и 2000 К, только заданные продукты."""
    sess = CeaSession(air_h2(), ProductOptions(only=tuple(ref.only_list("example1"))))
    blocks = ref.parse("example1")
    assert len(blocks) == 2
    total = 0
    for block in blocks:
        km = block.scalar("O/F")
        points = []
        for p_atm in (1.0, 0.1, 0.01):
            for t in (3000.0, 2000.0):
                r = sess.equilibrium("TP", Ratio.km(km), p=p_atm * ATM, t=t)
                assert r.converged, r.message
                points.append(r.point)
        total += compare_columns(block.rows, points, STATE_ROWS)
    assert total >= 2 * 6 * 8


def test_example2_tv_with_transport():
    """TV: та же смесь, φ = 1 (α = 1), T = 3000 К, заданные плотности; переносные свойства."""
    prop = Propellant((Component("H2", FUEL), Component("Air", OXIDIZER)))
    sess = CeaSession(prop, ProductOptions(only=tuple(ref.only_list("example2")), transport=True))
    block = ref.parse("example2")[0]
    points = []
    for rho_gcc in (9.1864e-05, 8.0877e-06, 6.6054e-07):
        r = sess.equilibrium("TV", Ratio.alpha(1.0), t=3000.0, v=1.0 / (rho_gcc * 1000.0))
        assert r.converged, r.message
        points.append(r.point)
    assert compare_columns(block.rows, points, STATE_ROWS) >= 3 * 8
    assert compare_transport(block, points) == 3 * 5


def test_example4_uv_assigned_energy_and_density():
    """UV: u/R = −45,1343, ρ = 14,428 кг/м³ — должно получиться состояние столбца 1 задачи №3."""
    prop = Propellant((
        Component("Air", OXIDIZER, amount=1.0, t0=700.0),
        Component("C7H8(L)", FUEL, amount=0.4, t0=298.15),
        Component("C8H18(L),n-octa", FUEL, amount=0.6, t0=298.15),
    ))
    sess = CeaSession(prop, ProductOptions(omit=tuple(ref.omit_list("example4")), trace=1e-15))
    r = sess.equilibrium("UV", Ratio.km(17.0), u=-45.1343 * R_UNIV, v=1.0 / 14.428)
    assert r.converged, r.message
    block = ref.parse("example4")[0]
    assert compare_columns(block.rows, [r.point], STATE_ROWS) >= 8
    assert close(r["p"], 100 * BAR, rel=1e-3)  # как в задаче №3


def test_example6_chapman_jouguet_detonation():
    prop = Propellant((Component("H2", FUEL), Component("O2", OXIDIZER)))
    sess = CeaSession(prop, ProductOptions(transport=True))
    res = sess.detonation(Ratio.alpha(1.0), t1=[298.15, 500.0], p1=[1 * BAR, 20 * BAR])
    assert res.converged, res.message
    block = ref.parse("example6")[0]
    init, prod = res.of_kind("det_initial"), res.of_kind("det_products")
    assert len(init) == len(prod) == 4
    n = compare_columns(block.section("UNBURNED GAS"), init, {
        "P1, BAR": ("p", 1 / BAR), "T1, K": ("t", 1.0), "H1, KJ/KG": ("i", 1e-3),
        "M1, (1/n)": ("mu_c", 1.0), "GAMMA1": ("k", 1.0), "SON VEL1,M/SEC": ("a", 1.0)}, abs_=1e-4)
    n += compare_columns(block.section("BURNED GAS"), prod, STATE_ROWS)
    n += compare_columns(block.section("DETONATION PARAMETERS"), prod, {
        "P/P1": ("p_ratio", 1.0), "T/T1": ("t_ratio", 1.0), "M/M1": ("mu_ratio", 1.0),
        "RHO/RHO1": ("rho_ratio", 1.0), "DET MACH NUMBER": ("M_D", 1.0), "DET VEL,M/SEC": ("D", 1.0)})
    assert n >= 4 * (6 + 8 + 6)
    assert compare_transport(block, prod) == 4 * 5


@pytest.mark.parametrize("frozen", [False, True])
def test_example7_incident_shock(frozen):
    prop = Propellant((Component("H2", MIXTURE, 0.05, 300.0), Component("O2", MIXTURE, 0.05, 300.0),
                       Component("Ar", MIXTURE, 0.90, 300.0)), basis="mole")
    sess = CeaSession(prop)
    u1 = [1100, 1200, 1250, 1300, 1350, 1400]
    res = sess.shock(None, 300.0, 10 * MMHG, u1=u1, incident="frozen" if frozen else "equilibrium")
    assert res.converged, res.message
    blocks = [b for b in ref.parse("example7") if ("FROZEN" in " ".join(b.text[:4])) == frozen]
    block = blocks[0]
    init, inc = res.of_kind("shock_initial"), res.of_kind("shock_incident")
    n = compare_columns(block.section("INITIAL GAS"), init, {
        "MACH NUMBER1": ("M", 1.0), "U1, M/SEC": ("w", 1.0), **STATE_ROWS})
    n += compare_columns(block.section("SHOCKED GAS"), inc, {
        "U2, M/SEC": ("w", 1.0), "P2/P1": ("p_ratio", 1.0), "T2/T1": ("t_ratio", 1.0),
        "M2/M1": ("mu_ratio", 1.0), "RHO2/RHO1": ("rho_ratio", 1.0), "V2, M/SEC": ("w_lab", 1.0),
        **STATE_ROWS})
    assert n >= 6 * (9 + 13)


def test_shock_reflected_is_consistent():
    """Отражённая волна: газ за ней неподвижен у стенки — скорость отражённой волны W₅ относительно газа 5
    и скорость набегания газа 2 связаны законом сохранения массы ρ₂·W₅ʹ = ρ₅·W₅."""
    prop = Propellant((Component("H2", MIXTURE, 0.05, 300.0), Component("O2", MIXTURE, 0.05, 300.0),
                       Component("Ar", MIXTURE, 0.90, 300.0)), basis="mole")
    res = CeaSession(prop).shock(None, 300.0, 10 * MMHG, u1=[1200.0], reflected="equilibrium")
    assert res.converged, res.message
    two, five = res.of_kind("shock_incident")[0], res.of_kind("shock_reflected")[0]
    assert five["p"] > two["p"] and five["t"] > two["t"]
    assert close(two["rho"] * five["w_refl"], five["rho"] * five["w"], rel=1e-6)
    assert close(five["rho_ratio"], five["rho"] / two["rho"], rel=1e-6)


@pytest.mark.parametrize("example, fac", [("example9", {"eps_k": 1.58}), ("example10", {"mass_flux": 1333.9})])
def test_finite_area_combustor(example, fac):
    prop = Propellant((Component("H2(L)", FUEL, t0=20.27), Component("O2(L)", OXIDIZER, t0=90.17)))
    res = CeaSession(prop).nozzle(Ratio.km(5.55157), 53.3172 * BAR, pk_p=[10, 100, 1000], eps=[25, 50, 75], **fac)
    assert res.converged, res.message
    blocks = ref.parse(example)
    assert len(blocks) == 2
    assert sum(compare_block(b, res.points) for b in blocks) > 100


def test_example11_ions_mole_basis_transport():
    prop = Propellant((Component("Li(cr)", FUEL, 1.0), Component("F2(L)", OXIDIZER, 0.5556, t0=85.02)),
                      basis="mole")
    sess = CeaSession(prop, ProductOptions(ions=True, transport=True))
    block = ref.parse("example11")[0]
    pk = block.value("P, BAR", 0) * BAR
    res = sess.nozzle(Ratio.km(block.scalar("O/F")), pk, pk_p=[68.0457], eps_sub=[10], eps=[10, 20, 100])
    assert res.converged, res.message
    assert compare_block(block, res.points) > 60
    # переносные свойства по столбцам эталона в порядке точек ядра
    assert compare_transport(block, res.points) == len(res.points) * 5
    assert any(sp.endswith("+") or sp.endswith("-") for p in res.points for sp in p.mole_fractions)


def test_example13_tripropellant_insert_trace():
    prop = Propellant((Component("N2H4(L)", FUEL, 80.0), Component("Be(a)", FUEL, 20.0),
                       Component("H2O2(L)", OXIDIZER, 100.0)))
    sess = CeaSession(prop, ProductOptions(insert=("BeO(L)",), trace=1e-10))
    block = ref.parse("example13")[0]
    assert close(block.scalar("O/F"), 33 / 67, rel=1e-12)   # %fuel = 67
    pk = block.value("P, BAR", 0) * BAR
    res = sess.nozzle(Ratio.km(33 / 67), pk, pk_p=[3, 10, 30, 300])
    assert res.converged, res.message
    assert compare_block(block, res.points) > 50
