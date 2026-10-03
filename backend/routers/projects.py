"""프로젝트(지원사업 등) 관리. 기업 PDF는 프로젝트 단위로 등록하고, 모든 목록 메뉴는
project_id로 그 프로젝트의 참여 기업만 조회한다 (PLAN.md Phase 9)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import auth_middleware as auth
from .. import storage
from ..models import Project, ProjectCompaniesInput, ProjectInput, ProjectRef

router = APIRouter(prefix="/api", tags=["projects"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean(data: ProjectInput, *, creating: bool, project_id: int | None = None) -> dict:
    values = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.model_dump(exclude_unset=True).items()}
    values = {k: (v if v != "" else None) for k, v in values.items()}
    if creating and not values.get("name"):
        raise HTTPException(status_code=422, detail="프로젝트명을 입력해 주세요.")
    if "name" in values:
        if not values["name"]:
            raise HTTPException(status_code=422, detail="프로젝트명을 입력해 주세요.")
        if storage.project_name_exists(values["name"], exclude_id=project_id):
            raise HTTPException(status_code=409, detail="같은 이름의 프로젝트가 이미 있습니다.")
    for key in ("start_date", "end_date"):
        if values.get(key) and not _DATE_RE.match(values[key]):
            raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD 형식으로 입력해 주세요.")
    current = storage.get_project(project_id) if project_id else {}
    start = values.get("start_date", (current or {}).get("start_date"))
    end = values.get("end_date", (current or {}).get("end_date"))
    if start and end and str(start)[:10] > str(end)[:10]:
        raise HTTPException(status_code=422, detail="지원기간 종료일은 시작일보다 빠를 수 없습니다.")
    return values


def require_project(project_id: int) -> dict:
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 프로젝트입니다.")
    return project


@router.get("/projects", response_model=list[Project])
def list_projects():
    return storage.list_projects()


@router.post("/projects", response_model=Project, status_code=201)
def create_project(data: ProjectInput):
    return storage.create_project(_clean(data, creating=True))


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: int):
    return require_project(project_id)


@router.patch("/projects/{project_id}", response_model=Project)
def update_project(project_id: int, data: ProjectInput):
    require_project(project_id)
    return storage.update_project(project_id, _clean(data, creating=False, project_id=project_id))


class PurgeConfirm(BaseModel):
    username: str = ""
    password: str = ""


@router.get("/projects/{project_id}/purge-preview")
def purge_preview(project_id: int):
    """전체 삭제 경고창용: 삭제될 기업 수·영업 기록 수."""
    require_project(project_id)
    return storage.project_purge_preview(project_id)


@router.post("/projects/{project_id}/purge")
def purge_project(project_id: int, data: PurgeConfirm):
    """프로젝트 삭제(유일한 삭제 방법): 등록 기업·원본 PDF·영업 관리 기록까지 지운다. 되돌릴 수 없으므로
    로그인 아이디·비밀번호를 다시 확인한다. 기업만 남기고 프로젝트만 지우는 API는 두지 않는다(사용자 결정 2026-10-03)."""
    project = require_project(project_id)
    if not auth.login_password():
        raise HTTPException(status_code=409, detail="비밀번호가 설정되지 않은 환경에서는 전체 삭제를 할 수 없습니다.")
    if not auth.check_credentials(data.username.strip(), data.password):
        # 401은 화면이 '로그인 만료'로 보고 로그인 화면으로 보내므로 403을 쓴다
        raise HTTPException(status_code=403, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    return {"project": project["name"], **storage.purge_project(project_id)}


@router.post("/projects/{project_id}/companies")
def add_companies(project_id: int, data: ProjectCompaniesInput):
    """이미 분석된 기업을 PDF 재업로드 없이 프로젝트에 추가."""
    require_project(project_id)
    known = {c.business_no for c in storage.list_companies()}
    unknown = [bn for bn in data.business_nos if bn not in known]
    if unknown:
        raise HTTPException(status_code=404, detail=f"등록되지 않은 사업자번호입니다: {', '.join(unknown[:5])}")
    return {"added": storage.add_companies_to_project(project_id, data.business_nos)}


@router.delete("/projects/{project_id}/companies/{business_no}", status_code=204)
def remove_company(project_id: int, business_no: str):
    """프로젝트 참여 명단에서만 제외. 기업 데이터는 유지."""
    require_project(project_id)
    if not storage.remove_company_from_project(project_id, business_no):
        raise HTTPException(status_code=404, detail="이 프로젝트에 참여하지 않은 기업입니다.")


@router.get("/companies/{business_no}/projects", response_model=list[ProjectRef])
def company_projects(business_no: str):
    return storage.projects_of_company(business_no)
