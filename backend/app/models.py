from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Trial(Base):
    __tablename__ = "trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    sample_type: Mapped[str] = mapped_column(String(80))
    curve_basis: Mapped[str] = mapped_column(String(10))  # volume or mass
    feed_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_residue: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    residue_density_g_cm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss_density_g_cm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparatus: Mapped[str] = mapped_column(String(120), default="Offline test data")
    source_note: Mapped[str] = mapped_column(Text, default="Offline laboratory record only")

    curve_points: Mapped[list["CurvePoint"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan", order_by="CurvePoint.recovery"
    )
    density_points: Mapped[list["DensityPoint"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan", order_by="DensityPoint.recovery"
    )
    plans: Mapped[list["Plan"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan"
    )


class CurvePoint(Base):
    __tablename__ = "curve_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.id"), index=True)
    recovery: Mapped[float] = mapped_column(Float)  # cumulative percent on curve_basis
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)

    trial: Mapped[Trial] = relationship(back_populates="curve_points")


class DensityPoint(Base):
    __tablename__ = "density_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.id"), index=True)
    recovery: Mapped[float] = mapped_column(Float)  # source recovery percent
    density_g_cm3: Mapped[float] = mapped_column(Float)  # g/cm3 at stated lab condition

    trial: Mapped[Trial] = relationship(back_populates="density_points")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    basis: Mapped[str] = mapped_column(String(10))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)

    trial: Mapped[Trial] = relationship(back_populates="plans")
