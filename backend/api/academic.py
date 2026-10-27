"""
Academic Hierarchy API Router — Institutional Structure & Course Organization.

This module exposes Nirma University's organizational hierarchy (Constituent
Institutes -> Academic Departments -> Degree Programs -> Batches -> Divisions)
to support scoped attribute-based access control (ABAC) and cascading group
targeting in outbound campaigns.

Endpoints:
    - GET /api/academic/tree: Complete nested hierarchical tree.
    - GET /api/academic/institutes: Flat list of constituent institutes (e.g. ITNU, IMNU).
    - GET /api/academic/departments: Departments filtered optionally by institute_id.
    - GET /api/academic/programs: Degree programs filtered optionally by department_id.

Dependencies:
    - fastapi >= 0.111
    - sqlalchemy >= 2.0
    - pydantic >= 2.0
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.auth import get_current_user
from backend.database.models import (
    AcademicAuditLog,
    AcademicBatch,
    AcademicDivision,
    AcademicProgram,
    Department,
    Institute,
    StaffUser,
)
from backend.database.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/academic", tags=["Academic Hierarchy"])


# ------------------------------------------------------------------------------
# Pydantic Schemas: Summary (Flat) Models
# ------------------------------------------------------------------------------
class DivisionSummary(BaseModel):
    """Schema for a class division (e.g. Division A, B)."""

    id: int
    batch_id: int
    code: str
    name: str
    current_semester: int
    is_active: bool


class BatchSummary(BaseModel):
    """Schema for an admission cohort batch (e.g. Batch of 2023-2027)."""

    id: int
    program_id: int
    admission_year: int
    graduating_year: int
    name: str
    is_current: bool


class ProgramSummary(BaseModel):
    """Schema for an academic degree program (e.g. B.Tech in CSE)."""

    id: int
    department_id: int
    code: str
    name: str
    level: str
    duration_semesters: int
    is_active: bool


class DepartmentSummary(BaseModel):
    """Schema for an academic department (e.g. Computer Science & Engineering)."""

    id: int
    institute_id: int
    code: str
    name: str
    hod_name: Optional[str] = None
    hod_email: Optional[str] = None
    is_active: bool


class InstituteSummary(BaseModel):
    """Schema for a constituent institute (e.g. Institute of Technology - ITNU)."""

    id: int
    code: str
    name: str
    contact_email: Optional[str] = None
    is_active: bool


# ------------------------------------------------------------------------------
# Pydantic Schemas: Nested Tree Models
# ------------------------------------------------------------------------------
class BatchTreeNode(BaseModel):
    id: int
    program_id: int
    admission_year: int
    graduating_year: int
    name: str
    is_current: bool
    divisions: List[DivisionSummary] = []


class ProgramTreeNode(BaseModel):
    id: int
    department_id: int
    code: str
    name: str
    level: str
    duration_semesters: int
    is_active: bool
    batches: List[BatchTreeNode] = []


class DepartmentTreeNode(BaseModel):
    id: int
    institute_id: int
    code: str
    name: str
    hod_name: Optional[str] = None
    hod_email: Optional[str] = None
    is_active: bool
    programs: List[ProgramTreeNode] = []


class InstituteTreeNode(BaseModel):
    id: int
    code: str
    name: str
    contact_email: Optional[str] = None
    is_active: bool
    departments: List[DepartmentTreeNode] = []


class AcademicTreeResponse(BaseModel):
    """Full nested academic tree representation for frontend cascading filters."""

    institutes: List[InstituteTreeNode]


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------
@router.get("/tree", response_model=AcademicTreeResponse)
async def get_academic_tree(
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_user),
) -> AcademicTreeResponse:
    """
    Returns the complete Nirma University academic hierarchy tree.

    Eagerly loads institutes, departments, programs, batches, and divisions
    in optimized sub-queries to prevent N+1 query overhead.

    Args:
        session: Active asynchronous SQLAlchemy session.
        _: Validated active StaffUser.

    Returns:
        AcademicTreeResponse containing all active constituent institutes and their branches.
    """
    stmt = (
        select(Institute)
        .where(Institute.is_active.is_(True))
        .options(
            selectinload(Institute.departments)
            .selectinload(Department.programs)
            .selectinload(AcademicProgram.batches)
            .selectinload(AcademicBatch.divisions)
        )
        .order_by(Institute.name)
    )
    res = await session.execute(stmt)
    institutes = res.scalars().all()

    inst_nodes: List[InstituteTreeNode] = []
    for inst in institutes:
        dept_nodes: List[DepartmentTreeNode] = []
        for dept in inst.departments:
            if not dept.is_active:
                continue
            prog_nodes: List[ProgramTreeNode] = []
            for prog in dept.programs:
                if not prog.is_active:
                    continue
                batch_nodes: List[BatchTreeNode] = []
                for bch in prog.batches:
                    div_items = [
                        DivisionSummary.model_validate(div, from_attributes=True)
                        for div in bch.divisions
                        if div.is_active
                    ]
                    batch_nodes.append(
                        BatchTreeNode(
                            id=bch.id,
                            program_id=bch.program_id,
                            admission_year=bch.admission_year,
                            graduating_year=bch.graduating_year,
                            name=bch.name,
                            is_current=bch.is_current,
                            divisions=div_items,
                        )
                    )

                prog_nodes.append(
                    ProgramTreeNode(
                        id=prog.id,
                        department_id=prog.department_id,
                        code=prog.code,
                        name=prog.name,
                        level=prog.level,
                        duration_semesters=prog.duration_semesters,
                        is_active=prog.is_active,
                        batches=batch_nodes,
                    )
                )

            dept_nodes.append(
                DepartmentTreeNode(
                    id=dept.id,
                    institute_id=dept.institute_id,
                    code=dept.code,
                    name=dept.name,
                    hod_name=dept.hod_name,
                    hod_email=dept.hod_email,
                    is_active=dept.is_active,
                    programs=prog_nodes,
                )
            )

        inst_nodes.append(
            InstituteTreeNode(
                id=inst.id,
                code=inst.code,
                name=inst.name,
                contact_email=inst.contact_email,
                is_active=inst.is_active,
                departments=dept_nodes,
            )
        )

    return AcademicTreeResponse(institutes=inst_nodes)


@router.get("/institutes", response_model=List[InstituteSummary])
async def list_institutes(
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_user),
) -> List[InstituteSummary]:
    """
    Lists all active constituent institutes of Nirma University.

    Args:
        session: Active asynchronous SQLAlchemy session.
        _: Authenticated staff user.

    Returns:
        List of InstituteSummary DTOs.
    """
    stmt = select(Institute).where(Institute.is_active.is_(True)).order_by(Institute.name)
    res = await session.execute(stmt)
    return [
        InstituteSummary(
            id=i.id,
            code=i.code,
            name=i.name,
            contact_email=i.contact_email,
            is_active=i.is_active,
        )
        for i in res.scalars().all()
    ]


@router.get("/departments", response_model=List[DepartmentSummary])
async def list_departments(
    institute_id: Optional[int] = Query(None, description="Filter by constituent institute ID"),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_user),
) -> List[DepartmentSummary]:
    """
    Lists academic departments, optionally scoped to a parent constituent institute.

    Args:
        institute_id: Optional foreign key to filter departments.
        session: Active asynchronous SQLAlchemy session.
        _: Authenticated staff user.

    Returns:
        List of DepartmentSummary DTOs.
    """
    stmt = select(Department).where(Department.is_active.is_(True))
    if institute_id is not None:
        stmt = stmt.where(Department.institute_id == institute_id)
    stmt = stmt.order_by(Department.name)
    res = await session.execute(stmt)
    return [
        DepartmentSummary(
            id=d.id,
            institute_id=d.institute_id,
            code=d.code,
            name=d.name,
            hod_name=d.hod_name,
            hod_email=d.hod_email,
            is_active=d.is_active,
        )
        for d in res.scalars().all()
    ]


@router.get("/programs", response_model=List[ProgramSummary])
async def list_programs(
    department_id: Optional[int] = Query(None, description="Filter by academic department ID"),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_user),
) -> List[ProgramSummary]:
    """
    Lists degree programs, optionally scoped to a parent academic department.

    Args:
        department_id: Optional foreign key to filter degree programs.
        session: Active asynchronous SQLAlchemy session.
        _: Authenticated staff user.

    Returns:
        List of ProgramSummary DTOs.
    """
    stmt = select(AcademicProgram).where(AcademicProgram.is_active.is_(True))
    if department_id is not None:
        stmt = stmt.where(AcademicProgram.department_id == department_id)
    stmt = stmt.order_by(AcademicProgram.name)
    res = await session.execute(stmt)
    return [
        ProgramSummary(
            id=p.id,
            department_id=p.department_id,
            code=p.code,
            name=p.name,
            level=p.level,
            duration_semesters=p.duration_semesters,
            is_active=p.is_active,
        )
        for p in res.scalars().all()
    ]


@router.get("/batches", response_model=List[BatchSummary])
async def list_batches(
    program_id: Optional[int] = Query(None, description="Filter by academic degree program ID"),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_user),
) -> List[BatchSummary]:
    """
    Lists admission cohort batches, optionally scoped to a degree program.

    Args:
        program_id: Optional degree program ID filter.
        session: Active asynchronous SQLAlchemy session.
        _: Authenticated staff user.

    Returns:
        List of BatchSummary DTOs.
    """
    stmt = select(AcademicBatch)
    if program_id is not None:
        stmt = stmt.where(AcademicBatch.program_id == program_id)
    stmt = stmt.order_by(AcademicBatch.admission_year.desc())
    res = await session.execute(stmt)
    return [
        BatchSummary(
            id=b.id,
            program_id=b.program_id,
            admission_year=b.admission_year,
            graduating_year=b.graduating_year,
            name=b.name,
            is_current=b.is_current,
        )
        for b in res.scalars().all()
    ]


@router.get("/divisions", response_model=List[DivisionSummary])
async def list_divisions(
    batch_id: Optional[int] = Query(None, description="Filter by cohort batch ID"),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_user),
) -> List[DivisionSummary]:
    """
    Lists academic class divisions, optionally scoped to an admission cohort batch.

    Args:
        batch_id: Optional cohort batch ID filter.
        session: Active asynchronous SQLAlchemy session.
        _: Authenticated staff user.

    Returns:
        List of DivisionSummary DTOs.
    """
    stmt = select(AcademicDivision).where(AcademicDivision.is_active.is_(True))
    if batch_id is not None:
        stmt = stmt.where(AcademicDivision.batch_id == batch_id)
    stmt = stmt.order_by(AcademicDivision.code)
    res = await session.execute(stmt)
    return [
        DivisionSummary(
            id=d.id,
            batch_id=d.batch_id,
            code=d.code,
            name=d.name,
            current_semester=d.current_semester,
            is_active=d.is_active,
        )
        for d in res.scalars().all()
    ]


class AcademicAuditLogResponse(BaseModel):
    """Compliance audit ledger response representation."""

    id: int
    action: str
    staff_id: Optional[int] = None
    staff_email: str
    staff_role: str
    institute_code: Optional[str] = None
    department_code: Optional[str] = None
    target_count: int
    target_filter: Optional[dict] = None
    campaign_id: Optional[int] = None
    created_at: datetime


class PaginatedAuditLogs(BaseModel):
    """Paginated list of academic compliance audit logs."""

    total: int
    page: int
    limit: int
    items: List[AcademicAuditLogResponse]


@router.get("/audit-logs", response_model=PaginatedAuditLogs)
async def list_academic_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    action: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> PaginatedAuditLogs:
    """
    Lists compliance audit logs scoped by user clearance role.

    - super_admin / admin: University-wide compliance ledger inspection.
    - dean: Clamped to audit logs of their constituent institute.
    - hod / operator: Clamped to audit logs of their department or own user ID.
    """
    stmt = select(AcademicAuditLog)
    if current_user.role not in ("admin", "super_admin"):
        if current_user.role == "dean" and current_user.institute_code:
            stmt = stmt.where(AcademicAuditLog.institute_code == current_user.institute_code)
        elif current_user.role in ("hod", "operator") and current_user.department_code:
            stmt = stmt.where(
                or_(
                    AcademicAuditLog.department_code == current_user.department_code,
                    AcademicAuditLog.staff_id == current_user.id,
                )
            )
        else:
            stmt = stmt.where(AcademicAuditLog.staff_id == current_user.id)

    if action:
        stmt = stmt.where(AcademicAuditLog.action == action)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Paginate
    stmt = stmt.order_by(AcademicAuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit)
    res = await session.execute(stmt)
    logs = res.scalars().all()

    return PaginatedAuditLogs(
        total=total,
        page=page,
        limit=limit,
        items=[AcademicAuditLogResponse.model_validate(l, from_attributes=True) for l in logs],
    )

