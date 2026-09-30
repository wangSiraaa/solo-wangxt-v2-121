from typing import Literal

from pydantic import BaseModel, Field

Basis = Literal["volume", "mass"]
Severity = Literal["error", "warning", "info"]


class CurvePointIn(BaseModel):
    recovery: float = Field(ge=0, le=100)
    temperature_c: float | None = Field(default=None, ge=-200, le=1000)


class CurvePointOut(CurvePointIn):
    pass


class DensityPointIn(BaseModel):
    recovery: float = Field(ge=0, le=100)
    density_g_cm3: float = Field(gt=0, lt=5)


class DensityPointOut(DensityPointIn):
    pass


class TrialBase(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    sample_type: str
    curve_basis: Basis
    feed_density: float | None = Field(default=None, gt=0, lt=5)
    measured_residue: float | None = Field(default=None, ge=0, le=100)
    measured_loss: float | None = Field(default=None, ge=0, le=100)
    residue_density_g_cm3: float | None = Field(default=None, gt=0, lt=5)
    loss_density_g_cm3: float | None = Field(default=None, gt=0, lt=5)
    apparatus: str = "Offline test data"
    source_note: str = "Offline laboratory record only"


class TrialCreate(TrialBase):
    curve_points: list[CurvePointIn] = Field(min_length=2)
    density_points: list[DensityPointIn] = Field(default_factory=list)


class TrialOut(TrialBase):
    id: int
    curve_points: list[CurvePointOut]
    density_points: list[DensityPointOut]

    model_config = {"from_attributes": True}


class FractionIn(BaseModel):
    name: str
    start: float | None = Field(default=None, ge=0, le=100)
    end: float | None = Field(default=None, ge=0, le=100)


class EvaluateRequest(BaseModel):
    basis: Basis
    fractions: list[FractionIn] = Field(min_length=1)
    plan_name: str | None = None
    save: bool = False


class FractionOut(BaseModel):
    name: str
    start: float | None
    end: float | None
    width: float | None = None
    source_start: float | None = None
    source_end: float | None = None
    start_temperature_c: float | None = None
    end_temperature_c: float | None = None
    average_density_g_cm3: float | None = None
    source_yield_percent: float | None = None
    target_yield_percent: float | None = None
    status: str


class Issue(BaseModel):
    severity: Severity
    code: str
    message: str


class Balance(BaseModel):
    fractions: float
    gaps: float
    residue: float | None
    loss: float | None
    unresolved: float | None
    total: float | None
    definition: str


class EvaluationResult(BaseModel):
    ok: bool
    basis: Basis
    curve_basis: Basis
    display_points: list[dict[str, float]] = Field(default_factory=list)
    measured_range: tuple[float | None, float | None]
    valid_interpolation_range: tuple[float | None, float | None]
    selected_interpolation_range: tuple[float | None, float | None] | None = None
    density_conversion: str
    fractions: list[FractionOut]
    overlaps: list[tuple[float, float]]
    gaps: list[tuple[float, float]]
    leading_gap: tuple[float, float] | None
    tail_gap: tuple[float, float] | None
    source_balance: Balance
    target_balance: Balance
    issues: list[Issue]
    method: dict[str, object]
    saved_plan_id: int | None = None


class PlanOut(BaseModel):
    id: int
    trial_id: int
    name: str
    basis: Basis
    valid: bool
    result: dict

    model_config = {"from_attributes": True}
