import csv
import io
import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from . import models
from .core import evaluate_plan
from .crud import create_trial, trial_to_dict, upsert_trial
from .database import Base, engine, get_db
from .schemas import (
    EvaluationResult,
    EvaluateRequest,
    PlanOut,
    TrialCreate,
    TrialOut,
)
from .seed_data import PLANS, TRIALS


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        for payload in TRIALS:
            existing = db.query(models.Trial).filter_by(code=payload["code"]).one_or_none()
            if existing is None:
                trial = create_trial(db, payload)
                template = PLANS.get(trial.code)
                if template:
                    result = evaluate_plan(trial_to_dict(trial), template)
                    db.add(models.Plan(
                        trial_id=trial.id,
                        name=template["name"],
                        basis=template["basis"],
                        result=result,
                        valid=result["ok"],
                    ))
                    db.commit()
    finally:
        db.close()
    yield


app = FastAPI(
    title="离线蒸馏曲线切点训练 API",
    version="1.0.0",
    description="只处理题目给定的离线试验记录；不连接、不控制真实装置。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "mode": "offline-lab-data-only"}


@app.get("/trials", response_model=list[TrialOut])
def list_trials(db: Session = Depends(get_db)):
    return db.query(models.Trial).order_by(models.Trial.id).all()


@app.get("/trials/{trial_id}", response_model=TrialOut)
def get_trial(trial_id: int, db: Session = Depends(get_db)):
    trial = db.get(models.Trial, trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Trial not found")
    return trial


@app.post("/trials", response_model=TrialOut, status_code=201)
def post_trial(payload: TrialCreate, db: Session = Depends(get_db)):
    if db.query(models.Trial).filter_by(code=payload.code).first():
        raise HTTPException(status_code=409, detail="试验编号已存在")
    return create_trial(db, payload.model_dump())


@app.post("/trials/{trial_id}/evaluate", response_model=EvaluationResult)
def evaluate(trial_id: int, request: EvaluateRequest, db: Session = Depends(get_db)):
    trial = db.get(models.Trial, trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Trial not found")
    result = evaluate_plan(trial_to_dict(trial), request.model_dump())
    if request.save:
        plan = models.Plan(
            trial_id=trial.id,
            name=request.plan_name or "未命名切点方案",
            basis=request.basis,
            result=result,
            valid=result["ok"],
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        result = {**result, "saved_plan_id": plan.id}
    return result


@app.get("/trials/{trial_id}/plans", response_model=list[PlanOut])
def list_plans(trial_id: int, db: Session = Depends(get_db)):
    if db.get(models.Trial, trial_id) is None:
        raise HTTPException(status_code=404, detail="Trial not found")
    return db.query(models.Plan).filter_by(trial_id=trial_id).order_by(models.Plan.id).all()


@app.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(models.Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@app.get("/plans/{plan_id}/export")
def export_plan(plan_id: int, format: str = "json", db: Session = Depends(get_db)):
    plan = db.get(models.Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    trial = plan.trial
    result = plan.result

    if format.lower() == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["# 离线蒸馏切点方案导出；不控制真实装置"])
        writer.writerow(["trial_code", trial.code, "trial_name", trial.name])
        writer.writerow(["plan", plan.name, "basis", plan.basis])
        writer.writerow(["temperature_interpolation", result["method"]["temperature_interpolation"]])
        writer.writerow(["density_model", result["method"]["density_model"]])
        writer.writerow(["applicable_scope", result["method"]["applicable_scope"]])
        writer.writerow([])
        writer.writerow(["fraction", "start_%", "end_%", "yield_selected_%", "yield_source_%", "start_T_C", "end_T_C", "avg_density_g_cm3", "status"])
        for row in result["fractions"]:
            writer.writerow([
                row["name"], row["start"], row["end"], row["target_yield_percent"],
                row["source_yield_percent"], row["start_temperature_c"],
                row["end_temperature_c"], row["average_density_g_cm3"], row["status"],
            ])
        writer.writerow([])
        writer.writerow(["balance", result["target_balance"]])
        writer.writerow(["issues"])
        for item in result["issues"]:
            writer.writerow([item["severity"], item["code"], item["message"]])
        content = buffer.getvalue().encode("utf-8-sig")
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="plan-{plan.id}.csv"'},
        )

    payload = {
        "offline_only": True,
        "trial": {
            "code": trial.code,
            "name": trial.name,
            "conditions": {
                "sample_type": trial.sample_type,
                "apparatus": trial.apparatus,
                "curve_basis": trial.curve_basis,
                "feed_density_g_cm3": trial.feed_density,
                "measured_residue_percent": trial.measured_residue,
                "measured_loss_percent": trial.measured_loss,
            },
        },
        "plan": {"name": plan.name, "basis": plan.basis},
        "result": result,
    }
    return StreamingResponse(
        io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="plan-{plan.id}.json"'},
    )
