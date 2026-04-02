from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from core.base_platform import Account, AccountStatus
from core.db import AccountModel, engine
from services.external_apps import install, list_status, start, start_all, stop, stop_all

router = APIRouter(prefix="/integrations", tags=["integrations"])


class BackfillRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["kiro"])
    account_ids: list[int] = Field(default_factory=list)
    pending_only: bool = False
    status: Optional[str] = None
    email: Optional[str] = None


def _to_account(model: AccountModel) -> Account:
    return Account(
        platform=model.platform,
        email=model.email,
        password=model.password,
        user_id=model.user_id,
        region=model.region,
        token=model.token,
        status=AccountStatus(model.status),
        extra=model.get_extra(),
    )


@router.get("/services")
def get_services():
    return {"items": list_status()}


@router.post("/services/start-all")
def start_all_services():
    return {"items": start_all()}


@router.post("/services/stop-all")
def stop_all_services():
    return {"items": stop_all()}


@router.post("/services/{name}/start")
def start_service(name: str):
    return start(name)


@router.post("/services/{name}/install")
def install_service(name: str):
    return install(name)


@router.post("/services/{name}/stop")
def stop_service(name: str):
    return stop(name)


@router.post("/backfill")
def backfill_integrations(body: BackfillRequest):
    summary = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "items": []}
    targets = set(body.platforms or [])

    with Session(engine) as session:
        query = select(AccountModel).where(AccountModel.platform == "kiro")

        if body.account_ids:
            query = query.where(AccountModel.id.in_(body.account_ids))
        elif targets and "kiro" not in targets:
            return summary

        if body.status:
            query = query.where(AccountModel.status == body.status)
        if body.email:
            query = query.where(AccountModel.email.contains(body.email))

        rows = session.exec(query).all()

        from services.external_sync import sync_account

        for row in rows:
            item = {"platform": row.platform, "email": row.email, "results": []}
            try:
                account = _to_account(row)
                results = sync_account(account)
                item["results"] = results
                if not results:
                    summary["skipped"] += 1
                elif all(bool(result.get("ok")) for result in results):
                    summary["success"] += 1
                else:
                    summary["failed"] += 1
            except Exception as exc:
                session.rollback()
                summary["failed"] += 1
                item["results"] = [{"name": "error", "ok": False, "msg": str(exc)}]

            summary["items"].append(item)
            summary["total"] += 1

    return summary
