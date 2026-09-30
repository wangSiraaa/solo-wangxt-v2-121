from sqlalchemy.orm import Session

from . import models


def trial_to_dict(trial: models.Trial) -> dict:
    return {
        "code": trial.code,
        "name": trial.name,
        "description": trial.description,
        "sample_type": trial.sample_type,
        "curve_basis": trial.curve_basis,
        "feed_density": trial.feed_density,
        "measured_residue": trial.measured_residue,
        "measured_loss": trial.measured_loss,
        "residue_density_g_cm3": trial.residue_density_g_cm3,
        "loss_density_g_cm3": trial.loss_density_g_cm3,
        "apparatus": trial.apparatus,
        "source_note": trial.source_note,
        "curve_points": [
            {"recovery": p.recovery, "temperature_c": p.temperature_c}
            for p in trial.curve_points
        ],
        "density_points": [
            {"recovery": p.recovery, "density_g_cm3": p.density_g_cm3}
            for p in trial.density_points
        ],
    }


def create_trial(db: Session, payload: dict) -> models.Trial:
    trial = models.Trial(**{k: v for k, v in payload.items() if k not in {"curve_points", "density_points"}})
    for point in payload["curve_points"]:
        trial.curve_points.append(models.CurvePoint(**point))
    for point in payload.get("density_points", []):
        trial.density_points.append(models.DensityPoint(**point))
    db.add(trial)
    db.commit()
    db.refresh(trial)
    return trial


def upsert_trial(db: Session, payload: dict) -> models.Trial:
    existing = db.query(models.Trial).filter_by(code=payload["code"]).one_or_none()
    if existing is None:
        return create_trial(db, payload)
    db.delete(existing)
    db.flush()
    return create_trial(db, payload)
