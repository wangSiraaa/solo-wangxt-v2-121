"""Distillation-curve validation, interpolation and cut-yield calculations.

All calculations operate on supplied offline laboratory records.  This module does
not read plant instruments and does not send set points to any process unit.
"""

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.interpolate import PchipInterpolator

EPS = 1.0e-9


def issue(severity: Literal["error", "warning", "info"], code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _numbers(values: list[float | None]) -> np.ndarray:
    return np.asarray(values, dtype=float)


@dataclass
class DensityProfile:
    """Piecewise-linear density versus source-basis cumulative recovery (%)."""

    x: np.ndarray
    rho: np.ndarray

    @classmethod
    def build(
        cls, points: list[dict[str, float]], x_max: float, issues: list[dict[str, str]]
    ) -> "DensityProfile | None":
        if not points:
            return None
        raw = sorted(((float(p["recovery"]), float(p["density_g_cm3"])) for p in points))
        x = np.array([p[0] for p in raw], dtype=float)
        rho = np.array([p[1] for p in raw], dtype=float)

        if np.any(rho <= 0):
            issues.append(issue("error", "density_nonpositive", "密度必须为正值。"))
            return None
        if len(x) < 2:
            issues.append(issue("warning", "density_single_point", "只有一个密度点，无法建立随馏分变化的密度关系。"))
            return None
        if np.any(np.diff(x) <= 0):
            issues.append(issue("error", "density_recovery_duplicate", "密度表中存在重复回收比例，无法定义单值密度函数。"))
            return None
        profile = cls(x, rho)
        if x[0] > 0.0 or x[-1] < x_max - 1.0e-8:
            issues.append(
                issue(
                    "warning",
                    "density_partial_range",
                    f"密度点仅覆盖 {x[0]:.2f}%–{x[-1]:.2f}%；不会向未覆盖区间外推。",
                )
            )
        return profile

    def covered(self, a: float, b: float) -> bool:
        return a >= self.x[0] - EPS and b <= self.x[-1] + EPS

    def integral(self, a: float, b: float, reciprocal: bool = False) -> float:
        """Analytically integrate rho dx or 1/rho dx over [a,b]."""
        if b < a - EPS:
            raise ValueError("integration interval reversed")
        a, b = max(float(a), float(self.x[0])), min(float(b), float(self.x[-1]))
        if b <= a + EPS:
            return 0.0
        if a < self.x[0] - EPS or b > self.x[-1] + EPS:
            raise ValueError("density integration outside covered range")

        total = 0.0
        for x0, x1, r0, r1 in zip(self.x[:-1], self.x[1:], self.rho[:-1], self.rho[1:]):
            lo, hi = max(a, x0), min(b, x1)
            if hi <= lo + EPS:
                continue
            if abs(r1 - r0) <= 1.0e-12:
                value = (hi - lo) / r0 if reciprocal else (hi - lo) * r0
            elif reciprocal:
                slope = (r1 - r0) / (x1 - x0)
                value = float(np.log((r0 + slope * (hi - x0)) / (r0 + slope * (lo - x0))) / slope)
            else:
                slope = (r1 - r0) / (x1 - x0)
                value = float(
                    0.5 * slope * (hi**2 - lo**2)
                    + (r0 - slope * x0) * (hi - lo)
                )
            total += value
        return float(total)


def _balance(
    fractions: float,
    gaps: float,
    residue: float | None,
    loss: float | None,
    unresolved: float | None,
    basis_label: str,
) -> dict[str, Any]:
    known = [fractions, gaps]
    for value in (residue, loss, unresolved):
        if value is not None:
            known.append(value)
    total = float(sum(known)) if all(v is not None for v in known) else None
    return {
        "fractions": round(float(fractions), 6),
        "gaps": round(float(gaps), 6),
        "residue": None if residue is None else round(float(residue), 6),
        "loss": None if loss is None else round(float(loss), 6),
        "unresolved": None if unresolved is None else round(float(unresolved), 6),
        "total": None if total is None else round(total, 6),
        "definition": (
            f"{basis_label}基准：所有已命名馏分（重叠只计一次）+ 未分配缺口/前段 + 残油 + 损失 = 100%；"
            "缺少残油或损失时用未拆分残余量闭合。"
        ),
    }


def _intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float] | None:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return (lo, hi) if hi > lo + EPS else None


def evaluate_plan(trial: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    basis = request["basis"]
    curve_basis = trial["curve_basis"]
    basis_label = "体积" if basis == "volume" else "质量"
    source_label = "体积" if curve_basis == "volume" else "质量"

    curve = sorted(trial["curve_points"], key=lambda p: float(p["recovery"]))
    recoveries = _numbers([p["recovery"] for p in curve])
    if len(recoveries) < 2:
        issues.append(issue("error", "curve_too_short", "累积蒸馏曲线至少需要两个回收比例点。"))
        return _failed_result(basis, curve_basis, issues)
    if np.any(np.diff(recoveries) <= 0):
        issues.append(issue("error", "recovery_not_increasing", "回收比例必须严格递增；请核实重复或倒退的试验点。"))
        return _failed_result(basis, curve_basis, issues)

    finite = [(float(x), float(p["temperature_c"])) for p, x in zip(curve, recoveries) if p["temperature_c"] is not None]
    finite_x = np.array([x for x, _ in finite], dtype=float)
    finite_t = np.array([t for _, t in finite], dtype=float)
    x_min_data, x_max = float(recoveries[0]), float(recoveries[-1])

    missing_temps = [float(x) for x, p in zip(recoveries, curve) if p["temperature_c"] is None]
    if finite_x.size:
        first_t, last_t = float(finite_x[0]), float(finite_x[-1])
        interior_missing = [x for x in missing_temps if first_t < x < last_t]
        if interior_missing:
            issues.append(issue("error", "interior_temperature_missing",
                                f"回收比例 {interior_missing} 的温度缺失，不能做内部插值。"))
            return _failed_result(basis, curve_basis, issues, (first_t, last_t))
        if first_t > 0.0 + EPS:
            issues.append(issue("info", "start_endpoint_missing",
                                f"缺少 0% 回收温度；温度插值从 {first_t:.2f}% 开始，不向低温侧外推。"))
    if finite_x.size < 2:
        issues.append(issue("error", "temperature_points_too_few", "至少需要两个带温度的曲线点。"))
        return _failed_result(basis, curve_basis, issues, (first_t if finite_x.size else None, x_max))
    if np.any(np.diff(finite_t) < -EPS):
        bad = [(float(x), float(t)) for x, t in zip(finite_x, finite_t)]
        issues.append(issue("error", "temperature_decreasing",
                            f"温度曲线出现下降：{bad}。PCHIP单调插值要求先核实并修正试验数据。"))
        return _failed_result(basis, curve_basis, issues, (first_t, x_max))
    if np.any(np.diff(finite_t) <= EPS):
        issues.append(issue("warning", "temperature_plateau", "存在温度平台；PCHIP会保留平台，但建议核实原始记录。"))

    residue_in = trial.get("measured_residue")
    loss_in = trial.get("measured_loss")
    residue_in = None if residue_in is None else float(residue_in)
    loss_in = None if loss_in is None else float(loss_in)
    if x_max > 100.0 + 0.5:
        issues.append(issue("error", "recovery_above_100", f"最大回收比例为 {x_max:.2f}%，超过100%，请先核实总量。"))
        return _failed_result(basis, curve_basis, issues, (first_t, x_max))
    if x_max < 90.0:
        issues.append(issue("warning", "low_recovered_total", f"最大回收比例仅 {x_max:.2f}%，残油/损失偏大，请核实。"))
    if residue_in is not None and loss_in is not None:
        closure = x_max + residue_in + loss_in
        if abs(closure - 100.0) > 0.5:
            sev = "error" if abs(closure - 100.0) > 1.0 else "warning"
            issues.append(issue(sev, "source_total_mismatch",
                                f"回收 {x_max:.2f}% + 残油 {residue_in:.2f}% + 损失 {loss_in:.2f}% = {closure:.2f}%，应按定义为100%。"))
    else:
        issues.append(issue("info", "residue_loss_unresolved",
                            "未同时给出残油和损失；未回收部分先作为未拆分残余量展示，不虚构损失。"))

    temperature = PchipInterpolator(finite_x, finite_t, extrapolate=False)
    density = DensityProfile.build(trial.get("density_points", []), x_max, issues)
    feed_density = trial.get("feed_density")
    feed_density = None if feed_density is None else float(feed_density)

    alternate = basis != curve_basis
    reciprocal = (curve_basis == "mass" and basis == "volume")
    conversion_required = alternate
    conversion_ready = True
    if conversion_required:
        missing_density_inputs = []
        if feed_density is None:
            missing_density_inputs.append("进料密度")
        if density is None:
            missing_density_inputs.append("至少两个随回收比例变化的密度点")
        elif not density.covered(0.0, x_max):
            missing_density_inputs.append(f"覆盖0%–{x_max:.2f}%的密度数据")
        if missing_density_inputs:
            conversion_ready = False
            issues.append(issue("error", "density_conversion_impossible",
                                "质量百分比与体积百分比不能共用同一横轴；需要" + "、".join(missing_density_inputs) + "，且不外推。"))

    # Source cumulative recovery -> selected basis cumulative recovery.
    source_grid: np.ndarray | None = None
    target_grid: np.ndarray | None = None
    if conversion_ready and alternate:
        breaks = [0.0, x_max]
        if density is not None:
            breaks.extend(float(v) for v in density.x if 0.0 <= v <= x_max)
        breaks.extend(np.arange(0.0, x_max + EPS, 0.02))
        source_grid = np.unique(np.round(np.asarray(breaks, dtype=float), 8))
        # rho(x) is piecewise linear. The direct-density integral is analytically
        # exact; use the same analytic routine for 1/rho rather than interpolating
        # mass and volume onto one common percentage axis.
        target_values = [0.0]
        factor = feed_density if reciprocal else 1.0 / feed_density
        for left, right in zip(source_grid[:-1], source_grid[1:]):
            integral = density.integral(float(left), float(right), reciprocal=reciprocal)
            target_values.append(target_values[-1] + factor * integral)
        target_grid = np.asarray(target_values, dtype=float)

    def to_source(v: float) -> float:
        if not alternate:
            return float(v)
        if target_grid is None or source_grid is None:
            return float("nan")
        return float(np.interp(v, target_grid, source_grid))

    def to_target(v: float) -> float:
        if not alternate:
            return float(v)
        if source_grid is None or target_grid is None:
            return float("nan")
        return float(np.interp(v, source_grid, target_grid))

    fractions_in = request["fractions"]
    prepared: list[dict[str, Any]] = []
    valid_intervals: list[tuple[float, float]] = []

    for item in fractions_in:
        name = str(item["name"])
        a_in, b_in = item.get("start"), item.get("end")
        out: dict[str, Any] = {
            "name": name,
            "start": a_in,
            "end": b_in,
            "width": None,
            "source_start": None,
            "source_end": None,
            "start_temperature_c": None,
            "end_temperature_c": None,
            "average_density_g_cm3": None,
            "source_yield_percent": None,
            "target_yield_percent": None,
            "status": "invalid",
        }
        if alternate and not conversion_ready:
            issues.append(issue("error", "fraction_evaluation_skipped",
                                f"馏分“{name}”未计算：质量/体积横轴换算所需密度数据不足。"))
            prepared.append(out)
            continue
        if a_in is None or b_in is None:
            issues.append(issue("error", "cut_endpoint_missing", f"馏分“{name}”缺少起点或终点，不能计算产率。"))
            prepared.append(out)
            continue
        a_in, b_in = float(a_in), float(b_in)
        a_src, b_src = to_source(a_in), to_source(b_in)
        out["source_start"], out["source_end"] = round(a_src, 6), round(b_src, 6)
        if a_src > b_src + EPS:
            issues.append(issue("error", "cut_reversed", f"馏分“{name}”的起点大于终点。"))
            prepared.append(out)
            continue
        if a_src < first_t - EPS or b_src > x_max + EPS:
            issues.append(issue("error", "cut_outside_data",
                                f"馏分“{name}”映射到源横轴 {a_src:.2f}%–{b_src:.2f}%，超出有温度/高温数据范围 {first_t:.2f}%–{x_max:.2f}%；不外推。"))
            prepared.append(out)
            continue
        if abs(a_src - b_src) <= EPS:
            out.update(
                status="zero_width",
                source_yield_percent=0.0,
                target_yield_percent=0.0,
                width=0.0,
            )
            t = temperature(np.array([a_src]))
            out["start_temperature_c"] = out["end_temperature_c"] = None if np.isnan(t[0]) else round(float(t[0]), 3)
            issues.append(issue("warning", "adjacent_cuts_equal",
                                f"馏分“{name}”的相邻切点相等，宽度和产率为0；请确认是否误输入。"))
            prepared.append(out)
            continue

        temperatures = temperature(np.array([a_src, b_src]))
        out["start_temperature_c"] = None if np.isnan(temperatures[0]) else round(float(temperatures[0]), 3)
        out["end_temperature_c"] = None if np.isnan(temperatures[1]) else round(float(temperatures[1]), 3)
        out["source_yield_percent"] = round(b_src - a_src, 6)
        if density is not None and density.covered(a_src, b_src):
            if curve_basis == "volume":
                avg_rho = density.integral(a_src, b_src) / (b_src - a_src)
            else:
                inv = density.integral(a_src, b_src, reciprocal=True)
                avg_rho = (b_src - a_src) / inv if inv > EPS else None
            out["average_density_g_cm3"] = None if avg_rho is None else round(avg_rho, 6)
        elif alternate:
            issues.append(issue("error", "fraction_density_missing",
                                f"馏分“{name}”缺少完整密度覆盖，不能进行质量/体积换算。"))
            prepared.append(out)
            continue

        if alternate:
            out["target_yield_percent"] = round(to_target(b_src) - to_target(a_src), 6)
        else:
            out["target_yield_percent"] = round(b_src - a_src, 6)
        out["width"] = round(float(b_in) - float(a_in), 6) if not alternate else out["target_yield_percent"]
        out["status"] = "ok"
        prepared.append(out)
        valid_intervals.append((a_src, b_src))

    # Pairwise overlaps and union of covered positive-width intervals.
    overlaps: list[tuple[float, float]] = []
    union: list[tuple[float, float]] = []
    for interval in sorted(valid_intervals):
        if not union or interval[0] > union[-1][1] + EPS:
            union.append((interval[0], interval[1]))
        else:
            overlap = _intervals_overlap(union[-1], interval)
            if overlap:
                overlaps.append(overlap)
            union[-1] = (union[-1][0], max(union[-1][1], interval[1]))
    if overlaps:
        shown = ", ".join(f"{a:.2f}%–{b:.2f}%" for a, b in overlaps)
        issues.append(issue("warning", "cut_overlap", f"切点区间存在重叠：{shown}。平衡表只计一次，但各馏分产率仍分别列出。"))

    # Gaps over source recovery. The portion before the first temperature is shown.
    gaps_src: list[tuple[float, float]] = []
    leading_gap = None
    tail_gap = None
    if union:
        if union[0][0] > EPS:
            leading_gap = (0.0, union[0][0])
        for prev, nxt in zip(union, union[1:]):
            if nxt[0] > prev[1] + EPS:
                gaps_src.append((prev[1], nxt[0]))
        if union[-1][1] < x_max - EPS:
            tail_gap = (union[-1][1], x_max)
    elif x_max > EPS:
        leading_gap = (0.0, x_max)

    all_gaps_src = ([leading_gap] if leading_gap else []) + gaps_src + ([tail_gap] if tail_gap else [])
    covered_source = sum(b - a for a, b in union)
    gaps_source = sum(b - a for a, b in all_gaps_src)

    # Target-basis unique fractions and gaps.
    covered_target = sum(to_target(b) - to_target(a) for a, b in union)
    gaps_target = sum(to_target(b) - to_target(a) for a, b in all_gaps_src)
    measured_distillate_target = to_target(x_max)

    residue_source = residue_in if residue_in is not None else None
    loss_source = loss_in if loss_in is not None else None
    unresolved_source = None
    if residue_source is None or loss_source is None:
        known_downstream = (residue_source or 0.0) + (loss_source or 0.0)
        unresolved_source = max(0.0, 100.0 - x_max - known_downstream)
        if residue_source is not None or loss_source is not None:
            issues.append(issue("warning", "partial_residue_loss",
                                "只提供了残油或损失中的一个；其余未回收量列为未拆分残余量。"))
    else:
        unresolved_source = 0.0 if abs(x_max + residue_source + loss_source - 100.0) <= 0.5 else None

    source_balance = _balance(
        covered_source, gaps_source, residue_source, loss_source, unresolved_source, source_label
    )

    residue_target = loss_target = unresolved_target = None
    if not alternate:
        residue_target, loss_target, unresolved_target = residue_source, loss_source, unresolved_source
    else:
        residue_density = trial.get("residue_density_g_cm3")
        loss_density = trial.get("loss_density_g_cm3")
        if residue_source is not None and loss_source is not None and feed_density and residue_density and loss_density:
            if curve_basis == "volume":
                residue_target = residue_source * float(residue_density) / feed_density
                loss_target = loss_source * float(loss_density) / feed_density
            else:
                residue_target = residue_source * feed_density / float(residue_density)
                loss_target = loss_source * feed_density / float(loss_density)
        else:
            unresolved_target = max(0.0, 100.0 - measured_distillate_target)
            if x_max + EPS < 100.0:
                issues.append(issue("warning", "target_residue_loss_unresolved",
                                    f"缺少{basis_label}基准残油/损失折算密度；{unresolved_target:.2f}%列为未拆分残余量。"))

    target_balance = _balance(
        covered_target, gaps_target, residue_target, loss_target, unresolved_target, basis_label
    )
    if target_balance["total"] is not None and abs(target_balance["total"] - 100.0) > 0.05:
        issues.append(issue("warning", "target_total_mismatch",
                            f"{basis_label}基准合计为 {target_balance['total']:.4f}%，不是100%。"))

    has_error = any(i["severity"] == "error" for i in issues)
    method = {
        "temperature_interpolation": "SciPy PCHIP（保形分段三次Hermite），extrapolate=False",
        "density_model": "密度按源回收比例分段线性变化，积分采用解析式；不使用首尾端点以外的密度外推。",
        "volume_to_mass": "体积回收横轴 x 时，累计质量% = ∫ρ馏分/ρ进料 dx。",
        "mass_to_volume": "质量回收横轴 x 时，累计体积% = ∫ρ进料/ρ馏分 dx。",
        "source_curve_basis": curve_basis,
        "selected_basis": basis,
        "applicable_scope": {
            "temperature_source_recovery_percent": [round(first_t, 6), round(x_max, 6)],
            "density_source_recovery_percent": [round(float(density.x[0]), 6), round(float(density.x[-1]), 6)] if density is not None else None,
            "no_high_temperature_extrapolation": True,
            "offline_only": True,
        },
        "balance_rule": "重叠区间平衡时只计一次；缺口、残油、损失或未拆分残余量均显式列出。",
    }

    display_points = []
    for src_x, temp in zip(finite_x, finite_t):
        display_points.append({
            "source_recovery_percent": round(float(src_x), 6),
            "selected_recovery_percent": round(to_target(float(src_x)), 6),
            "temperature_c": round(float(temp), 4),
        })

    return {
        "ok": not has_error,
        "basis": basis,
        "curve_basis": curve_basis,
        "display_points": display_points,
        "measured_range": [round(x_min_data, 6), round(x_max, 6)],
        "valid_interpolation_range": [round(first_t, 6), round(x_max, 6)],
        "selected_interpolation_range": [
            round(to_target(first_t), 6),
            round(to_target(x_max), 6),
        ],
        "density_conversion": (
            "未换算（选择横轴与曲线基准相同）"
            if not alternate
            else f"基于随回收比例变化密度的解析积分：{source_label}% → {basis_label}%"
        ),
        "fractions": prepared,
        "overlaps": [[round(a, 6), round(b, 6)] for a, b in overlaps],
        "gaps": [[round(a, 6), round(b, 6)] for a, b in gaps_src],
        "leading_gap": [round(leading_gap[0], 6), round(leading_gap[1], 6)] if leading_gap else None,
        "tail_gap": [round(tail_gap[0], 6), round(tail_gap[1], 6)] if tail_gap else None,
        "source_balance": source_balance,
        "target_balance": target_balance,
        "issues": issues,
        "method": method,
        "saved_plan_id": None,
    }


def _failed_result(
    basis: str,
    curve_basis: str,
    issues: list[dict[str, str]],
    temp_range: tuple[float | None, float | None] = (None, None),
) -> dict[str, Any]:
    empty_balance = _balance(0, 0, None, None, None, "体积" if basis == "volume" else "质量")
    return {
        "ok": False,
        "basis": basis,
        "curve_basis": curve_basis,
        "display_points": [],
        "measured_range": [None, None],
        "valid_interpolation_range": [temp_range[0], temp_range[1]],
        "density_conversion": "未计算",
        "fractions": [],
        "overlaps": [],
        "gaps": [],
        "leading_gap": None,
        "tail_gap": None,
        "source_balance": empty_balance,
        "target_balance": empty_balance,
        "issues": issues,
        "method": {"offline_only": True, "no_high_temperature_extrapolation": True},
        "saved_plan_id": None,
    }
