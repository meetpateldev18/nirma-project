"""
Student Lookup & Bulk Roster Ingestion API Router.

Provides:
1. Scoped single-student lookup for individual call outreach.
2. Enterprise CSV / Roster bulk ingestion pipeline mapping ERP student spreadsheets
   (TCS iON / MyNirma) to the normalized academic tree with automated roll number parsing.
3. Multi-tenant Attribute-Based Access Control (ABAC) across Admin, Dean, HoD,
   Class Coordinator, and Faculty Operator roles.

Endpoints:
    - GET /api/students/search: Scoped name/roll/phone search.
    - POST /api/students/upload: Bulk CSV student roster ingestion.
    - GET /api/students/template: Downloadable CSV template for university staff.

Dependencies:
    - fastapi >= 0.111
    - sqlalchemy >= 2.0
    - pydantic >= 2.0
"""

import csv
import io
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
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
    Student,
)
from backend.database.session import get_async_session, set_rls_session_context
from backend.utils.roll_parser import parse_nirma_roll

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/students", tags=["Students"])


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------
class StudentSearchResult(BaseModel):
    """Student identity, academic scoping, and standing metrics for recipient selection."""

    id: int
    name: str
    roll_number: str
    phone: str
    department: Optional[str] = None
    semester: Optional[int] = None
    institute_id: Optional[int] = None
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    division_id: Optional[int] = None
    institute_code: Optional[str] = None
    department_code: Optional[str] = None
    program_code: Optional[str] = None
    division_code: Optional[str] = None
    lab_batch: Optional[str] = None
    attendance_pct: Optional[float] = None
    pending_fee_inr: Optional[float] = None


class PaginatedStudents(BaseModel):
    """Paginated student directory representation."""

    total: int
    page: int
    limit: int
    items: List[StudentSearchResult]


class RosterIngestionResponse(BaseModel):
    """Summary metrics of a bulk student spreadsheet upload."""

    total_rows: int
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = []


# ------------------------------------------------------------------------------
# Helper Utilities
# ------------------------------------------------------------------------------
def _map_student(s: Student) -> StudentSearchResult:
    """Transforms a Student ORM instance into StudentSearchResult DTO with relationships."""
    return StudentSearchResult(
        id=s.id,
        name=s.name,
        roll_number=s.roll_number,
        phone=s.phone,
        department=s.department,
        semester=s.semester,
        institute_id=s.institute_id,
        department_id=s.department_id,
        program_id=s.program_id,
        division_id=s.division_id,
        institute_code=s.institute_rel.code if s.institute_rel else None,
        department_code=s.department_rel.code if s.department_rel else None,
        program_code=s.program_rel.code if s.program_rel else None,
        division_code=s.division_rel.code if s.division_rel else None,
        lab_batch=s.lab_batch,
        attendance_pct=float(s.attendance_pct) if s.attendance_pct is not None else None,
        pending_fee_inr=float(s.pending_fee_inr) if s.pending_fee_inr is not None else None,
    )
def normalize_column_name(col: str) -> str:
    """Strips punctuation and whitespace to compare CSV header aliases uniformly."""
    return re.sub(r"[^a-z0-9]", "", col.strip().lower())


def normalize_phone_number(raw_phone: str) -> Optional[str]:
    """Cleans phone numbers into E.164 compliant format (defaulting to +91)."""
    digits = re.sub(r"[^\d]", "", raw_phone)
    if not digits:
        return None
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if 10 <= len(digits) <= 15:
        return f"+{digits}"
    return None


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------
@router.get("/search", response_model=List[StudentSearchResult])
async def search_students(
    q: str = Query(..., min_length=2, max_length=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> List[StudentSearchResult]:
    """
    Matches active students by name, roll number, or phone number.

    Enforces multi-tier Attribute-Based Access Control (ABAC):
    - super_admin / admin: University-wide discovery.
    - dean: Clamped to assigned constituent institute.
    - hod / operator: Clamped to assigned academic department.
    - class_coordinator: Clamped to assigned division.
    - faculty_mentor: Clamped to assigned mentee cohort.
    """
    await set_rls_session_context(
        session=session,
        role=current_user.role,
        user_id=current_user.id,
        institute_id=current_user.institute_id,
        department_id=current_user.department_id,
        program_id=current_user.program_id,
        division_id=current_user.division_id,
    )
    term = f"%{q.strip()}%"
    await set_rls_session_context(
        session=session,
        role=current_user.role,
        user_id=current_user.id,
        institute_id=current_user.institute_id,
        department_id=current_user.department_id,
        program_id=current_user.program_id,
        division_id=current_user.division_id,
    )
    stmt = (
        select(Student)
        .options(
            selectinload(Student.institute_rel),
            selectinload(Student.department_rel),
            selectinload(Student.program_rel),
            selectinload(Student.division_rel),
        )
        .where(
            Student.is_active.is_(True),
            or_(
                Student.name.ilike(term),
                Student.roll_number.ilike(term),
                Student.phone.ilike(term),
            ),
        )
    )

    # Multi-tenant ABAC scoping
    if current_user.role not in ("admin", "super_admin"):
        if current_user.role == "dean":
            if current_user.institute_id:
                stmt = stmt.where(Student.institute_id == current_user.institute_id)
        elif current_user.role in ("hod", "operator"):
            if current_user.department_id:
                dept_filter = [Student.department_id == current_user.department_id]
                if current_user.department_code:
                    dept_filter.append(Student.department.ilike(f"%{current_user.department_code}%"))
                stmt = stmt.where(or_(*dept_filter))
            elif current_user.institute_id:
                stmt = stmt.where(Student.institute_id == current_user.institute_id)
        elif current_user.role == "program_coordinator":
            if current_user.program_id:
                stmt = stmt.where(Student.program_id == current_user.program_id)
            elif current_user.department_id:
                stmt = stmt.where(Student.department_id == current_user.department_id)
        elif current_user.role == "class_coordinator":
            if current_user.division_id:
                stmt = stmt.where(Student.division_id == current_user.division_id)
            elif current_user.department_id:
                stmt = stmt.where(Student.department_id == current_user.department_id)
        elif current_user.role == "faculty_mentor":
            stmt = stmt.where(Student.mentor_id == current_user.id)

    stmt = stmt.order_by(Student.name).limit(10)
    res = await session.execute(stmt)
    students = res.scalars().all()
    return [_map_student(s) for s in students]


@router.get("", response_model=PaginatedStudents)
async def list_students(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=100, description="Page size"),
    institute_id: Optional[int] = Query(None, description="Filter by constituent institute ID"),
    department_id: Optional[int] = Query(None, description="Filter by academic department ID"),
    program_id: Optional[int] = Query(None, description="Filter by degree program ID"),
    batch_id: Optional[int] = Query(None, description="Filter by cohort batch ID"),
    division_id: Optional[int] = Query(None, description="Filter by division ID"),
    semester: Optional[int] = Query(None, ge=1, le=10, description="Filter by current semester"),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> PaginatedStudents:
    """
    Lists active students with pagination and academic hierarchy filters.

    Strictly enforces multi-tier Attribute-Based Access Control (ABAC):
    - super_admin / admin: Unrestricted query access across all institutes and departments.
    - dean: Clamped to students enrolled in their assigned constituent institute.
    - hod / operator: Clamped to students enrolled in their assigned academic department.
    - class_coordinator: Clamped to students enrolled in their assigned division.
    - faculty_mentor: Clamped to students assigned to their mentee cohort.
    """
    await set_rls_session_context(
        session=session,
        role=current_user.role,
        user_id=current_user.id,
        institute_id=current_user.institute_id,
        department_id=current_user.department_id,
        program_id=current_user.program_id,
        division_id=current_user.division_id,
    )
    stmt = (
        select(Student)
        .options(
            selectinload(Student.institute_rel),
            selectinload(Student.department_rel),
            selectinload(Student.program_rel),
            selectinload(Student.division_rel),
        )
        .where(Student.is_active.is_(True))
    )

    # 1. Multi-tenant ABAC scoping
    if current_user.role not in ("admin", "super_admin"):
        if current_user.role == "dean":
            if current_user.institute_id:
                stmt = stmt.where(Student.institute_id == current_user.institute_id)
        elif current_user.role in ("hod", "operator"):
            if current_user.department_id:
                dept_filter = [Student.department_id == current_user.department_id]
                if current_user.department_code:
                    dept_filter.append(Student.department.ilike(f"%{current_user.department_code}%"))
                stmt = stmt.where(or_(*dept_filter))
            elif current_user.institute_id:
                stmt = stmt.where(Student.institute_id == current_user.institute_id)
        elif current_user.role == "program_coordinator":
            if current_user.program_id:
                stmt = stmt.where(Student.program_id == current_user.program_id)
            elif current_user.department_id:
                stmt = stmt.where(Student.department_id == current_user.department_id)
        elif current_user.role == "class_coordinator":
            if current_user.division_id:
                stmt = stmt.where(Student.division_id == current_user.division_id)
            elif current_user.department_id:
                stmt = stmt.where(Student.department_id == current_user.department_id)
        elif current_user.role == "faculty_mentor":
            stmt = stmt.where(Student.mentor_id == current_user.id)

    # 2. User Query Filters (within authorized scope)
    if institute_id is not None and current_user.role in ("admin", "super_admin"):
        stmt = stmt.where(Student.institute_id == institute_id)
    if department_id is not None and current_user.role in ("admin", "super_admin", "dean"):
        stmt = stmt.where(Student.department_id == department_id)
    if program_id is not None:
        stmt = stmt.where(Student.program_id == program_id)
    if batch_id is not None:
        stmt = stmt.where(Student.batch_id == batch_id)
    if division_id is not None and current_user.role != "class_coordinator":
        stmt = stmt.where(Student.division_id == division_id)
    if semester is not None:
        stmt = stmt.where(Student.semester == semester)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    # Paginate
    stmt = stmt.order_by(Student.roll_number).offset((page - 1) * limit).limit(limit)
    res = await session.execute(stmt)
    students = res.scalars().all()

    return PaginatedStudents(
        total=total,
        page=page,
        limit=limit,
        items=[_map_student(s) for s in students],
    )





@router.get("/template")
async def download_roster_template() -> Response:
    """Returns a pre-formatted sample CSV template for university student roster uploads."""
    sample_csv = (
        "roll_number,name,phone,alt_phone,division,lab_batch,semester,attendance_pct,pending_fee_inr,language_pref\n"
        "23BCE045,Aarav Patel,+919876500001,+919876599901,A,A2,6,68.5,0.00,gu\n"
        "23BCE112,Diya Shah,+919876500002,,B,B1,6,84.0,45000.00,hi\n"
        "23BAI012,Rohan Mehta,+919876500003,,A,A1,6,92.0,0.00,en\n"
        "22MBA104,Ananya Desai,+919876500005,,A,,4,95.0,0.00,en\n"
        "23BME019,Kavya Sharma,+919876500004,,A,,6,72.0,12000.00,hi\n"
    )
    return Response(
        content=sample_csv,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="nirma_student_roster_template.csv"'},
    )


@router.get("/{student_id}", response_model=StudentSearchResult)
async def get_student_by_id(
    student_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> StudentSearchResult:
    """
    Retrieves full academic profile for a single student by primary key ID.

    Enforces ABAC boundaries:
    - 404 NOT FOUND if student does not exist or is inactive.
    - 403 FORBIDDEN if requesting user lacks clearance for student's institute/dept/division.
    """
    await set_rls_session_context(
        session=session,
        role=current_user.role,
        user_id=current_user.id,
        institute_id=current_user.institute_id,
        department_id=current_user.department_id,
        program_id=current_user.program_id,
        division_id=current_user.division_id,
    )
    stmt = (
        select(Student)
        .options(
            selectinload(Student.institute_rel),
            selectinload(Student.department_rel),
            selectinload(Student.program_rel),
            selectinload(Student.division_rel),
        )
        .where(Student.id == student_id, Student.is_active.is_(True))
    )
    res = await session.execute(stmt)
    student = res.scalar_one_or_none()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student ID {student_id} not found or inactive.",
        )

    # ABAC boundary validation
    if current_user.role not in ("admin", "super_admin"):
        if current_user.role == "dean":
            if current_user.institute_id and student.institute_id != current_user.institute_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Student belongs to another constituent institute.",
                )
        elif current_user.role in ("hod", "operator"):
            dept_matches = False
            if current_user.department_id and student.department_id == current_user.department_id:
                dept_matches = True
            elif current_user.department_code:
                user_dept = current_user.department_code.lower()
                stud_dept = (student.department or "").lower()
                # Check text alias match (e.g. 'cs' in 'cse' or 'cse' in 'computer science')
                if stud_dept and (user_dept in stud_dept or stud_dept in user_dept):
                    dept_matches = True
                elif student.department_rel and (
                    user_dept == student.department_rel.code.lower()
                    or user_dept in student.department_rel.name.lower()
                ):
                    dept_matches = True
                else:
                    # Check via roll number taxonomy
                    roll_info = parse_nirma_roll(student.roll_number)
                    if roll_info.is_valid and roll_info.department_code:
                        if roll_info.department_code.lower() == user_dept or roll_info.department_code.lower() in user_dept or user_dept in roll_info.department_code.lower():
                            dept_matches = True
            elif not current_user.department_id and current_user.institute_id and student.institute_id == current_user.institute_id:
                dept_matches = True

            if not dept_matches:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Student belongs to another academic department.",
                )
        elif current_user.role == "program_coordinator":
            if current_user.program_id and student.program_id != current_user.program_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Student belongs to another academic program.",
                )
        elif current_user.role == "class_coordinator":
            if current_user.division_id and student.division_id != current_user.division_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Student belongs to another academic division.",
                )
        elif current_user.role == "faculty_mentor":
            if student.mentor_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Student is not assigned to your mentee cohort.",
                )

    return _map_student(student)


@router.post("/upload", response_model=RosterIngestionResponse, status_code=status.HTTP_200_OK)
async def upload_students_csv(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> RosterIngestionResponse:
    """
    Bulk student roster ingestion endpoint for ERP / SIS spreadsheets.

    Decomposes roll numbers via `parse_nirma_roll`, resolves institutional branches,
    enforces ABAC boundaries, upserts student profiles, and logs an immutable audit event.
    """
    filename = file.filename or "roster.csv"
    if not (filename.endswith(".csv") or filename.endswith(".txt")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a comma-separated values (.csv) or text file.",
        )

    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = raw_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to decode file. Please ensure UTF-8 encoding.",
            )

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded CSV file is empty.")

    # Header Alias Map
    header_map: Dict[str, str] = {}
    for raw_header in reader.fieldnames:
        norm = normalize_column_name(raw_header)
        if norm in ("rollnumber", "rollno", "roll", "studentid", "studentroll"):
            header_map["roll"] = raw_header
        elif norm in ("name", "studentname", "fullname"):
            header_map["name"] = raw_header
        elif norm in ("phone", "phonenumber", "mobile", "contact", "contactno"):
            header_map["phone"] = raw_header
        elif norm in ("altphone", "parentphone", "emergencyphone", "emergencycontact"):
            header_map["alt_phone"] = raw_header
        elif norm in ("department", "dept", "branch"):
            header_map["department"] = raw_header
        elif norm in ("semester", "sem", "currentsemester"):
            header_map["semester"] = raw_header
        elif norm in ("division", "div", "section", "classdivision"):
            header_map["division"] = raw_header
        elif norm in ("labbatch", "batch", "practicalbatch"):
            header_map["lab_batch"] = raw_header
        elif norm in ("attendancepct", "attendance", "attendancepercentage", "attd"):
            header_map["attendance"] = raw_header
        elif norm in ("pendingfeeinr", "pendingfee", "feedue", "fee"):
            header_map["pending_fee"] = raw_header
        elif norm in ("languagepref", "language", "lang", "preferredlanguage"):
            header_map["language"] = raw_header

    if "roll" not in header_map or "name" not in header_map or "phone" not in header_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "CSV must contain at least 'roll_number', 'name', and 'phone' columns. "
                "Download the template for the required format."
            ),
        )

    # Pre-cache academic hierarchy nodes for rapid in-memory FK resolution
    institutes_res = await session.execute(select(Institute))
    institutes_by_code = {i.code: i for i in institutes_res.scalars().all()}

    departments_res = await session.execute(select(Department))
    departments_by_code = {d.code: d for d in departments_res.scalars().all()}

    programs_res = await session.execute(select(AcademicProgram))
    programs_by_code = {p.code: p for p in programs_res.scalars().all()}

    batches_res = await session.execute(select(AcademicBatch))
    batches_by_prog_year = {(b.program_id, b.admission_year): b for b in batches_res.scalars().all()}

    divisions_res = await session.execute(select(AcademicDivision))
    divisions_by_batch_code = {(d.batch_id, d.code): d for d in divisions_res.scalars().all()}

    inserted = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    total_rows = 0

    for idx, row in enumerate(reader, start=2):
        total_rows += 1
        roll_raw = row.get(header_map["roll"], "").strip()
        name_raw = row.get(header_map["name"], "").strip()
        phone_raw = row.get(header_map["phone"], "").strip()

        if not roll_raw or not name_raw or not phone_raw:
            skipped += 1
            errors.append(f"Row {idx}: Missing mandatory roll, name, or phone.")
            continue

        # 1. Parse roll taxonomy
        roll_info = parse_nirma_roll(roll_raw)
        if not roll_info.is_valid:
            skipped += 1
            errors.append(f"Row {idx}: {roll_info.error_message}")
            continue

        # 2. Enforce ABAC security scope
        if current_user.role not in ("admin", "super_admin"):
            if current_user.role == "dean" and current_user.institute_code != roll_info.institute_code:
                skipped += 1
                errors.append(
                    f"Row {idx} ({roll_raw}): Belongs to {roll_info.institute_code}; "
                    f"unauthorized for Dean of {current_user.institute_code}."
                )
                continue
            if current_user.role in ("hod", "operator") and current_user.department_code != roll_info.department_code:
                skipped += 1
                errors.append(
                    f"Row {idx} ({roll_raw}): Belongs to {roll_info.department_code}; "
                    f"unauthorized for {current_user.role} of {current_user.department_code}."
                )
                continue
            if current_user.role == "program_coordinator" and current_user.department_code and current_user.department_code != roll_info.department_code:
                skipped += 1
                errors.append(
                    f"Row {idx} ({roll_raw}): Belongs to {roll_info.department_code}; "
                    f"unauthorized for Program Coordinator."
                )
                continue

        # 3. Clean & validate phone number
        phone_clean = normalize_phone_number(phone_raw)
        if not phone_clean:
            skipped += 1
            errors.append(f"Row {idx} ({roll_raw}): Invalid phone number '{phone_raw}'.")
            continue

        alt_phone_clean = None
        if "alt_phone" in header_map and row.get(header_map["alt_phone"]):
            alt_phone_clean = normalize_phone_number(row[header_map["alt_phone"]])

        # 4. Resolve / provision academic hierarchy foreign keys
        inst_obj = institutes_by_code.get(roll_info.institute_code or "")
        dept_obj = departments_by_code.get(roll_info.department_code or "")
        prog_obj = programs_by_code.get(roll_info.program_code or "")

        batch_id: Optional[int] = None
        if prog_obj and roll_info.admission_year:
            batch_key = (prog_obj.id, roll_info.admission_year)
            batch_obj = batches_by_prog_year.get(batch_key)
            if not batch_obj:
                grad_year = roll_info.admission_year + (prog_obj.duration_semesters // 2)
                batch_obj = AcademicBatch(
                    program_id=prog_obj.id,
                    admission_year=roll_info.admission_year,
                    graduating_year=grad_year,
                    name=f"Batch of {roll_info.admission_year}-{grad_year}",
                    is_current=True,
                )
                session.add(batch_obj)
                await session.flush()
                batches_by_prog_year[batch_key] = batch_obj
            batch_id = batch_obj.id

        # 5. Class division matching
        div_code_raw = row.get(header_map["division"], "").strip().upper() if "division" in header_map else None
        division_id: Optional[int] = None
        if batch_id and div_code_raw:
            div_key = (batch_id, div_code_raw)
            div_obj = divisions_by_batch_code.get(div_key)
            if not div_obj:
                div_obj = AcademicDivision(
                    batch_id=batch_id,
                    code=div_code_raw,
                    name=f"Division {div_code_raw}",
                    current_semester=6,
                    is_active=True,
                )
                session.add(div_obj)
                await session.flush()
                divisions_by_batch_code[div_key] = div_obj
            division_id = div_obj.id

        # 6. Parse numeric metrics (semester, attendance, pending fees)
        sem_val = None
        if "semester" in header_map and row.get(header_map["semester"]):
            try:
                sem_val = int(row[header_map["semester"]])
            except ValueError:
                pass

        attd_val = 100.0
        if "attendance" in header_map and row.get(header_map["attendance"]):
            try:
                attd_val = float(re.sub(r"[^\d.]", "", row[header_map["attendance"]]))
            except ValueError:
                pass

        fee_val = 0.0
        if "pending_fee" in header_map and row.get(header_map["pending_fee"]):
            try:
                fee_val = float(re.sub(r"[^\d.]", "", row[header_map["pending_fee"]]))
            except ValueError:
                pass

        lang_val = "hi"
        if "language" in header_map and row.get(header_map["language"]):
            cleaned_lang = row[header_map["language"]].strip().lower()
            if cleaned_lang in ("en", "english"):
                lang_val = "en"
            elif cleaned_lang in ("gu", "gujarati"):
                lang_val = "gu"
            elif cleaned_lang in ("hi", "hindi"):
                lang_val = "hi"

        lab_batch_val = row.get(header_map["lab_batch"], "").strip() if "lab_batch" in header_map else None

        # 7. Upsert student record
        stmt = select(Student).where(Student.roll_number == roll_info.raw_roll)
        existing_student = (await session.execute(stmt)).scalar_one_or_none()

        if existing_student:
            existing_student.name = name_raw
            existing_student.phone = phone_clean
            if alt_phone_clean:
                existing_student.alt_phone = alt_phone_clean
            if sem_val is not None:
                existing_student.semester = sem_val
            if lab_batch_val:
                existing_student.lab_batch = lab_batch_val
            existing_student.attendance_pct = attd_val
            existing_student.pending_fee_inr = fee_val
            existing_student.language_pref = lang_val
            if inst_obj:
                existing_student.institute_id = inst_obj.id
            if dept_obj:
                existing_student.department_id = dept_obj.id
                existing_student.department = dept_obj.name
            if prog_obj:
                existing_student.program_id = prog_obj.id
            if batch_id:
                existing_student.batch_id = batch_id
            if division_id:
                existing_student.division_id = division_id
            updated += 1
        else:
            new_student = Student(
                roll_number=roll_info.raw_roll,
                name=name_raw,
                phone=phone_clean,
                alt_phone=alt_phone_clean,
                language_pref=lang_val,
                department=dept_obj.name if dept_obj else (roll_info.department_code or None),
                semester=sem_val or 1,
                institute_id=inst_obj.id if inst_obj else None,
                department_id=dept_obj.id if dept_obj else None,
                program_id=prog_obj.id if prog_obj else None,
                batch_id=batch_id,
                division_id=division_id,
                lab_batch=lab_batch_val,
                attendance_pct=attd_val,
                pending_fee_inr=fee_val,
                is_active=True,
            )
            session.add(new_student)
            inserted += 1

    # 8. Record Immutable Academic Audit Trail Entry
    audit_entry = AcademicAuditLog(
        action="student_roster_uploaded",
        staff_id=current_user.id,
        staff_email=current_user.email,
        staff_role=current_user.role,
        institute_code=current_user.institute_code,
        department_code=current_user.department_code,
        target_count=inserted + updated,
        target_filter={
            "filename": filename,
            "total_rows": total_rows,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
        },
        ip_address=request.client.host if request.client else None,
    )
    session.add(audit_entry)

    await session.commit()
    logger.info(
        "Roster upload completed by %s: %d inserted, %d updated, %d skipped.",
        current_user.email,
        inserted,
        updated,
        skipped,
    )

    return RosterIngestionResponse(
        total_rows=total_rows,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=errors[:15],
    )



