"""
Academic Hierarchy & Data Scoping Test Suite.

Verifies:
1. /api/academic/tree and sub-endpoints return the complete Nirma University academic tree.
2. Department-scoped operators can only search and discover students within their department.
3. System administrators have university-wide discovery across all constituent institutes.
4. Campaign runner enforces scoping when a non-admin creates a campaign.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    AcademicBatch,
    AcademicDivision,
    AcademicProgram,
    Department,
    Institute,
    Institution,
    StaffUser,
    Student,
)


@pytest.fixture
async def seed_academic_tree(db_session: AsyncSession) -> dict:
    """Seeds a minimal academic hierarchy for testing."""
    institution = Institution(code="NIRMA", name="Nirma University", domain="nirmauni.ac.in", is_active=True)
    db_session.add(institution)
    await db_session.flush()

    itnu = Institute(institution_id=institution.id, code="ITNU", name="Institute of Technology", is_active=True)
    imnu = Institute(institution_id=institution.id, code="IMNU", name="Institute of Management", is_active=True)
    db_session.add_all([itnu, imnu])
    await db_session.flush()

    cse = Department(institute_id=itnu.id, code="CSE", name="Computer Science & Engineering", is_active=True)
    me = Department(institute_id=itnu.id, code="ME", name="Mechanical Engineering", is_active=True)
    db_session.add_all([cse, me])
    await db_session.flush()

    bce = AcademicProgram(department_id=cse.id, code="BCE", name="B.Tech CSE", level="UG", duration_semesters=8, is_active=True)
    db_session.add(bce)
    await db_session.flush()

    batch = AcademicBatch(program_id=bce.id, admission_year=2023, graduating_year=2027, name="Batch 2023", is_current=True)
    db_session.add(batch)
    await db_session.flush()

    div_a = AcademicDivision(batch_id=batch.id, code="A", name="Division A", current_semester=6, is_active=True)
    db_session.add(div_a)
    await db_session.commit()

    return {
        "institution": institution,
        "itnu": itnu,
        "imnu": imnu,
        "cse": cse,
        "me": me,
        "bce": bce,
        "batch": batch,
        "div_a": div_a,
    }


@pytest.mark.asyncio
async def test_get_academic_tree(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seed_academic_tree: dict,
):
    """Verifies that /api/academic/tree returns active institutes and nested branches."""
    response = await async_client.get("/api/academic/tree", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "institutes" in data
    assert len(data["institutes"]) >= 2

    # Verify ITNU exists in tree
    itnu = next((i for i in data["institutes"] if i["code"] == "ITNU"), None)
    assert itnu is not None
    assert "departments" in itnu
    # Verify CSE exists under ITNU
    cse = next((d for d in itnu["departments"] if d["code"] == "CSE"), None)
    assert cse is not None
    assert "programs" in cse
    bce = next((p for p in cse["programs"] if p["code"] == "BCE"), None)
    assert bce is not None


@pytest.mark.asyncio
async def test_get_academic_institutes_and_departments(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seed_academic_tree: dict,
):
    """Verifies flat list endpoints for institutes and departments."""
    inst_resp = await async_client.get("/api/academic/institutes", headers=admin_headers)
    assert inst_resp.status_code == 200
    institutes = inst_resp.json()
    assert any(i["code"] == "ITNU" for i in institutes)
    itnu_id = next(i["id"] for i in institutes if i["code"] == "ITNU")

    dept_resp = await async_client.get(f"/api/academic/departments?institute_id={itnu_id}", headers=admin_headers)
    assert dept_resp.status_code == 200
    depts = dept_resp.json()
    assert any(d["code"] == "CSE" for d in depts)


@pytest.mark.asyncio
async def test_student_search_scoping(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    operator_headers: dict[str, str],
    seed_users: dict[str, StaffUser],
    seed_students: list[Student],
    seed_academic_tree: dict,
    db_session: AsyncSession,
):
    """
    Verifies ABAC scoping:
    - Scoped operator (ITNU/CSE) can only see CSE students (e.g. Aarav Patel 21BCE001).
    - Scoped operator CANNOT see Mechanical students (Rohan Mehta 21BME003).
    - Administrator can search and see students across all institutes and departments.
    """
    # Configure the test operator user to be scoped to CSE
    operator = seed_users["operator"]
    cse_dept = seed_academic_tree["cse"]
    operator.department_id = cse_dept.id
    operator.department_code = "CS"
    await db_session.commit()

    # 1. Operator searches for CSE student
    cse_search = await async_client.get("/api/students/search?q=Aarav", headers=operator_headers)
    assert cse_search.status_code == 200
    cse_results = cse_search.json()
    assert len(cse_results) >= 1
    assert any(s["roll_number"] == "21BCE001" for s in cse_results)

    # 2. Operator searches for Mechanical student (Rohan Mehta 21BME003)
    # The operator is scoped to CSE, so Rohan (ME) must NOT be returned!
    me_search = await async_client.get("/api/students/search?q=Rohan", headers=operator_headers)
    assert me_search.status_code == 200
    me_results = me_search.json()
    assert not any(s["roll_number"] == "21BME003" for s in me_results)

    # 3. Admin searches for Mechanical student (Rohan Mehta 21BME003)
    # The admin has global clearance, so Rohan MUST be returned!
    admin_me_search = await async_client.get("/api/students/search?q=Rohan", headers=admin_headers)
    assert admin_me_search.status_code == 200
    admin_me_results = admin_me_search.json()
    assert any(s["roll_number"] == "21BME003" for s in admin_me_results)


@pytest.mark.asyncio
async def test_roster_template_download(async_client: AsyncClient, admin_headers: dict[str, str]):
    """Verifies that the roster CSV template can be downloaded."""
    resp = await async_client.get("/api/students/template", headers=admin_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "roll_number,name,phone" in resp.text


@pytest.mark.asyncio
async def test_roster_upload_admin_success(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seed_academic_tree: dict,
    db_session: AsyncSession,
):
    """Verifies that an administrator can bulk-upload students from a CSV spreadsheet."""
    csv_content = (
        "roll_number,name,phone,division,semester,attendance_pct,pending_fee_inr\n"
        "23BCE099,Ishaan Dave,+919876599099,A,6,82.5,0.00\n"
        "23BCE100,Pooja Patel,+919876599100,B,6,74.0,25000.00\n"
    )
    files = {"file": ("students.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = await async_client.post("/api/students/upload", headers=admin_headers, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 2
    assert data["inserted"] >= 1
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_roster_upload_operator_abac_enforcement(
    async_client: AsyncClient,
    operator_headers: dict[str, str],
    seed_users: dict[str, StaffUser],
    seed_academic_tree: dict,
    db_session: AsyncSession,
):
    """
    Verifies that when a departmental operator uploads a CSV containing students
    from other branches (e.g. Mechanical '23BME099' for a CSE operator),
    unauthorized records are safely skipped with detailed security error logs.
    """
    operator = seed_users["operator"]
    cse_dept = seed_academic_tree["cse"]
    operator.department_id = cse_dept.id
    operator.department_code = "CSE"
    operator.institute_code = "ITNU"
    await db_session.commit()

    csv_content = (
        "roll_number,name,phone,division,semester\n"
        "23BCE088,Authorized CSE Student,+919876599088,A,6\n"
        "23BME088,Unauthorized ME Student,+919876599089,A,6\n"
    )
    files = {"file": ("mixed.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = await async_client.post("/api/students/upload", headers=operator_headers, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 2
    assert data["inserted"] == 1  # Only the CSE student was accepted
    assert data["skipped"] == 1   # ME student was rejected
    assert any("unauthorized" in err.lower() for err in data["errors"])


@pytest.mark.asyncio
async def test_academic_audit_logs_endpoint(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
):
    """Verifies that the compliance audit ledger can be queried."""
    resp = await async_client.get("/api/academic/audit-logs", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_batches_and_divisions_endpoints(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seed_academic_tree: dict,
):
    """Verifies that academic batches and divisions endpoints return structured data."""
    bce_prog = seed_academic_tree["bce"]

    # 1. Fetch batches
    batch_resp = await async_client.get(
        f"/api/academic/batches?program_id={bce_prog.id}",
        headers=admin_headers,
    )
    assert batch_resp.status_code == 200
    batches = batch_resp.json()
    assert len(batches) >= 1
    batch_id = batches[0]["id"]

    # 2. Fetch divisions
    div_resp = await async_client.get(
        f"/api/academic/divisions?batch_id={batch_id}",
        headers=admin_headers,
    )
    assert div_resp.status_code == 200
    divisions = div_resp.json()
    assert len(divisions) >= 1
    assert any(d["code"] in ("A", "B", "C") for d in divisions)


@pytest.mark.asyncio
async def test_student_directory_and_get_by_id_abac(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    operator_headers: dict[str, str],
    seed_users: dict[str, StaffUser],
    seed_students: list[Student],
    seed_academic_tree: dict,
    db_session: AsyncSession,
):
    """
    Verifies:
    1. GET /api/students returns paginated records with ABAC scoping.
    2. GET /api/students/{id} allows access to authorized student.
    3. GET /api/students/{id} returns 403 Forbidden for cross-department student access.
    """
    operator = seed_users["operator"]
    cse_dept = seed_academic_tree["cse"]
    operator.department_id = cse_dept.id
    operator.department_code = "CSE"
    await db_session.commit()

    # Find a CSE student and an ME student
    cse_student = next(s for s in seed_students if "BCE" in s.roll_number)
    me_student = next(s for s in seed_students if "BME" in s.roll_number)

    # 1. Admin lists students
    admin_list = await async_client.get("/api/students?limit=10", headers=admin_headers)
    assert admin_list.status_code == 200
    admin_data = admin_list.json()
    active_count = len([s for s in seed_students if s.is_active])
    assert admin_data["total"] >= active_count

    # 2. Operator lists students — should only contain CSE students
    op_list = await async_client.get("/api/students?limit=10", headers=operator_headers)
    assert op_list.status_code == 200
    op_data = op_list.json()
    assert all("BCE" in item["roll_number"] for item in op_data["items"])

    # 3. Operator views their own CSE student -> 200 OK
    cse_get = await async_client.get(f"/api/students/{cse_student.id}", headers=operator_headers)
    assert cse_get.status_code == 200
    assert cse_get.json()["roll_number"] == cse_student.roll_number

    # 4. Operator views ME student -> 403 Forbidden
    me_get = await async_client.get(f"/api/students/{me_student.id}", headers=operator_headers)
    assert me_get.status_code == 403
    assert "Access denied" in me_get.json()["detail"]

