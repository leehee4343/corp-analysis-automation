"""프로젝트(지원사업 등) 관리. 기업 PDF는 프로젝트 단위로 등록하고, 모든 목록 메뉴는
project_id로 그 프로젝트의 참여 기업만 조회한다 (PLAN.md Phase 9)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

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
    if creating:
        values.setdefault("status", "진행중")
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


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int):
    """프로젝트와 참여 명단만 삭제. 기업 분석 데이터·원본 PDF는 남는다."""
    if not storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="존재하지 않는 프로젝트입니다.")


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
