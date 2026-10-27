"""
Database Seeding Script — Initial Administrative User & Production Call Script Templates.

This script populates the database with:
1. Default system administrator credentials ('admin@nirmauni.ac.in').
2. The 6 standardized multilingual call script templates defined in the PRD:
   - Fee Reminder (Hindi)
   - Exam Notification (English)
   - Attendance Alert (Gujarati / Hindi)
   - Event Announcement (English)
   - Placement Notice (English)
   - General Inquiry (Multilingual)

Usage:
    python -m backend.seeds
"""

import asyncio
import logging
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.models import (
    Base,
    CallScript,
    StaffUser,
    Institution,
    Institute,
    Department,
    AcademicProgram,
    AcademicBatch,
    AcademicDivision,
    Student,
)
from backend.database.session import async_engine, async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

INITIAL_TEMPLATES = [
    {
        "name": "Fee Reminder — Hindi",
        "category": "fee_reminder",
        "language": "hi",
        "opening_message": (
            "Namaste, main Nirma University se automated assistant bol raha hoon. "
            "Aapki semester fees ka payment abhi baaki hai. Kya aap iske baare mein baat kar sakte hain?"
        ),
        "system_prompt": (
            "You are a polite college fee reminder voice assistant of Nirma University speaking in Hindi. "
            "Your goal is to inform the student about their pending semester fee and inquire when they will pay. "
            "CRITICAL INSTRUCTIONS: "
            "1. Answer in maximum 2 short sentences (under 30 words). "
            "2. Never use bullet points, asterisks, formatting, or lists. This is a voice call. "
            "3. If the student confirms a payment date, acknowledge politely and conclude the call."
        ),
    },
    {
        "name": "Exam Schedule Notification — English",
        "category": "exam_notice",
        "language": "en",
        "opening_message": (
            "Hello, this is an automated notification from Nirma University Examination Cell. "
            "Your upcoming semester end examination timetable has been published on the student portal."
        ),
        "system_prompt": (
            "You are a professional examination coordinator voice assistant of Nirma University speaking in English. "
            "Your goal is to ensure the student is aware of their upcoming examination schedule and hall ticket availability. "
            "CRITICAL INSTRUCTIONS: "
            "1. Answer in maximum 2 short sentences (under 30 words). "
            "2. Never use bullet points, markdown, or lists. "
            "3. Answer basic questions about exam dates and portal downloads, then politely end the call."
        ),
    },
    {
        "name": "Attendance Alert — Gujarati",
        "category": "attendance_alert",
        "language": "gu",
        "opening_message": (
            "Namaste, hu Nirma University mathi automated call kari rahyo chhu. "
            "Aapni haajari current semester ma niyamit karta ochi chhe. Shu tame aa babate vat kari shako chho?"
        ),
        "system_prompt": (
            "You are an academic advisor voice assistant of Nirma University speaking in Gujarati. "
            "Your goal is to warn the student about their low attendance and inform them about university criteria. "
            "CRITICAL INSTRUCTIONS: "
            "1. Answer in maximum 2 short sentences (under 30 words) in clean Gujarati. "
            "2. Never use bullet points, markdown, or lists. "
            "3. Inquire politely about the reason for absence and advise meeting their faculty mentor."
        ),
    },
    {
        "name": "Event Announcement — English",
        "category": "event_announcement",
        "language": "en",
        "opening_message": (
            "Hello, this is an automated announcement from Nirma University. "
            "The annual technical symposium and cultural festival registration is now open."
        ),
        "system_prompt": (
            "You are an energetic event coordinator voice assistant of Nirma University speaking in English. "
            "Your goal is to inform students about campus fest registrations, key dates, and venue details. "
            "CRITICAL INSTRUCTIONS: "
            "1. Keep answers concise (max 2 short sentences, under 30 words). "
            "2. Never use bullet points or markdown symbols. "
            "3. Take confirmation if the student plans to participate."
        ),
    },
    {
        "name": "Campus Placement Drive — English",
        "category": "placement_notice",
        "language": "en",
        "opening_message": (
            "Hello, this is the Nirma University Corporate Relations and Placement Cell calling. "
            "An upcoming campus placement drive has been scheduled for eligible final year students."
        ),
        "system_prompt": (
            "You are a placement office voice assistant of Nirma University speaking in English. "
            "Your goal is to notify eligible students of company recruitment drives, eligibility, and reporting times. "
            "CRITICAL INSTRUCTIONS: "
            "1. Keep responses under 30 words (2 short sentences max). "
            "2. Avoid any markdown or symbols. "
            "3. Emphasize formal dress code and resume requirements."
        ),
    },
    {
        "name": "General Administrative Inquiry — Multilingual",
        "category": "general_inquiry",
        "language": "hi",
        "opening_message": (
            "Namaste, main Nirma University prashasan se automated assistant bol raha hoon. "
            "Main aapki sahayata ke liye uplabdh hoon. Aap kis vishay mein jaankari chahte hain?"
        ),
        "system_prompt": (
            "You are a helpful general administrative voice assistant of Nirma University capable of speaking in Hindi, Gujarati, or English. "
            "Answer student queries politely and concisely regarding university office hours, certificates, and student portal access. "
            "CRITICAL INSTRUCTIONS: "
            "1. Respond in the exact language the student uses (Hindi, Gujarati, or English). "
            "2. Maximum 2 short sentences per response (under 35 words). "
            "3. Never output markdown formatting or bullet points."
        ),
    },
]


async def seed_data(session: AsyncSession) -> None:
    """
    Seeds initial admin user and predefined call templates into the database.

    Args:
        session: Active asynchronous SQLAlchemy database session.
    """
    # 1. Seed Administrative User
    admin_email = "admin@nirmauni.ac.in"
    stmt = select(StaffUser).where(StaffUser.email == admin_email)
    result = await session.execute(stmt)
    existing_admin = result.scalar_one_or_none()

    if not existing_admin:
        admin_user = StaffUser(
            email=admin_email,
            name="Nirma System Administrator",
            role="admin",
            password_hash=pwd_context.hash("Admin@Nirma2026"),
            is_active=True,
        )
        session.add(admin_user)
        await session.flush()
        logger.info("Created default administrator: %s", admin_email)
        admin_id = admin_user.id
    else:
        logger.info("Administrator '%s' already exists.", admin_email)
        admin_id = existing_admin.id

    # 2. Seed Call Script Templates
    for template_data in INITIAL_TEMPLATES:
        stmt = select(CallScript).where(CallScript.name == template_data["name"])
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            script = CallScript(
                name=template_data["name"],
                category=template_data["category"],
                language=template_data["language"],
                opening_message=template_data["opening_message"],
                system_prompt=template_data["system_prompt"],
                is_active=True,
                created_by=admin_id,
            )
            session.add(script)
            logger.info("Seeded template: %s", template_data["name"])

    # 3. Seed Real-World Nirma University Academic Tree
    await seed_academic_hierarchy(session, admin_id)

    await session.commit()
    logger.info("Database seeding completed successfully.")


async def seed_academic_hierarchy(session: AsyncSession, admin_id: int) -> None:
    """Populates Nirma University constituent institutes, departments, programs, and batches."""
    # A. Root Institution
    inst_stmt = select(Institution).where(Institution.code == "NIRMA")
    inst = (await session.execute(inst_stmt)).scalar_one_or_none()
    if not inst:
        inst = Institution(
            code="NIRMA",
            name="Nirma University",
            domain="nirmauni.ac.in",
            is_active=True,
        )
        session.add(inst)
        await session.flush()
        logger.info("Seeded Institution: Nirma University")

    # B. Constituent Institutes
    INSTITUTES_DATA = [
        {"code": "ITNU", "name": "Institute of Technology", "email": "director.it@nirmauni.ac.in"},
        {"code": "IMNU", "name": "Institute of Management", "email": "director.im@nirmauni.ac.in"},
        {"code": "IPNU", "name": "Institute of Pharmacy", "email": "director.ip@nirmauni.ac.in"},
        {"code": "ISNU", "name": "Institute of Science", "email": "director.is@nirmauni.ac.in"},
        {"code": "ILNU", "name": "Institute of Law", "email": "director.il@nirmauni.ac.in"},
        {"code": "IAPNU", "name": "Institute of Architecture & Planning", "email": "director.iap@nirmauni.ac.in"},
        {"code": "ICNU", "name": "Institute of Commerce", "email": "director.ic@nirmauni.ac.in"},
        {"code": "IDNU", "name": "Institute of Design", "email": "director.id@nirmauni.ac.in"},
        {"code": "FDSR", "name": "Faculty of Doctoral Studies & Research", "email": "dean.fdsr@nirmauni.ac.in"},
    ]

    institutes_map: dict[str, Institute] = {}
    for i_data in INSTITUTES_DATA:
        stmt = select(Institute).where(Institute.code == i_data["code"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            new_inst = Institute(
                institution_id=inst.id,
                code=i_data["code"],
                name=i_data["name"],
                contact_email=i_data["email"],
                is_active=True,
            )
            session.add(new_inst)
            await session.flush()
            institutes_map[i_data["code"]] = new_inst
            logger.info("Seeded Institute: %s (%s)", i_data["name"], i_data["code"])
        else:
            institutes_map[i_data["code"]] = existing

    # C. Seed Departments Across All Institutes
    ALL_DEPARTMENTS_CONFIG = [
        # ITNU
        {"inst": "ITNU", "code": "CSE", "name": "Computer Science & Engineering", "email": "hod.cse@nirmauni.ac.in"},
        {"inst": "ITNU", "code": "ECE", "name": "Electronics & Communication Engineering", "email": "hod.ece@nirmauni.ac.in"},
        {"inst": "ITNU", "code": "EE", "name": "Electrical Engineering", "email": "hod.ee@nirmauni.ac.in"},
        {"inst": "ITNU", "code": "ME", "name": "Mechanical Engineering", "email": "hod.me@nirmauni.ac.in"},
        {"inst": "ITNU", "code": "CL", "name": "Civil Engineering", "email": "hod.cl@nirmauni.ac.in"},
        {"inst": "ITNU", "code": "CH", "name": "Chemical Engineering", "email": "hod.ch@nirmauni.ac.in"},
        {"inst": "ITNU", "code": "IC", "name": "Instrumentation & Control Engineering", "email": "hod.ic@nirmauni.ac.in"},
        # IMNU
        {"inst": "IMNU", "code": "DMS", "name": "Department of Management Studies", "email": "hod.dms@nirmauni.ac.in"},
        # IPNU
        {"inst": "IPNU", "code": "DPS", "name": "Department of Pharmaceutical Sciences", "email": "hod.dps@nirmauni.ac.in"},
        # ISNU
        {"inst": "ISNU", "code": "DBS", "name": "Department of Biological Sciences", "email": "hod.dbs@nirmauni.ac.in"},
        {"inst": "ISNU", "code": "DCH", "name": "Department of Chemistry", "email": "hod.dch@nirmauni.ac.in"},
        # ILNU
        {"inst": "ILNU", "code": "DOL", "name": "Department of Law", "email": "hod.dol@nirmauni.ac.in"},
        # IAPNU
        {"inst": "IAPNU", "code": "DOA", "name": "Department of Architecture", "email": "hod.doa@nirmauni.ac.in"},
        {"inst": "IAPNU", "code": "DOP", "name": "Department of Planning", "email": "hod.dop@nirmauni.ac.in"},
        # ICNU
        {"inst": "ICNU", "code": "DOC", "name": "Department of Commerce", "email": "hod.doc@nirmauni.ac.in"},
        # IDNU
        {"inst": "IDNU", "code": "DOD", "name": "Department of Design", "email": "hod.dod@nirmauni.ac.in"},
        # FDSR
        {"inst": "FDSR", "code": "DSR", "name": "Faculty of Doctoral Studies & Research", "email": "dean.fdsr@nirmauni.ac.in"},
    ]

    dept_map: dict[str, Department] = {}
    for d_data in ALL_DEPARTMENTS_CONFIG:
        parent_inst = institutes_map.get(d_data["inst"])
        if not parent_inst:
            continue
        stmt = select(Department).where(Department.institute_id == parent_inst.id, Department.code == d_data["code"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            dept = Department(
                institute_id=parent_inst.id,
                code=d_data["code"],
                name=d_data["name"],
                hod_email=d_data["email"],
                is_active=True,
            )
            session.add(dept)
            await session.flush()
            dept_map[f"{d_data['inst']}_{d_data['code']}"] = dept
            logger.info("Seeded Department: %s (%s) under %s", d_data["name"], d_data["code"], d_data["inst"])
        else:
            dept_map[f"{d_data['inst']}_{d_data['code']}"] = existing

    # D. Seed Degree Programs Across Departments
    ALL_PROGRAMS_CONFIG = [
        # ITNU CSE
        {"dept": "ITNU_CSE", "code": "BCE", "name": "B.Tech in Computer Science & Engineering", "level": "UG", "semesters": 8},
        {"dept": "ITNU_CSE", "code": "BAI", "name": "B.Tech in CSE (Artificial Intelligence & ML)", "level": "UG", "semesters": 8},
        {"dept": "ITNU_CSE", "code": "MCE", "name": "M.Tech in Computer Science & Engineering", "level": "PG", "semesters": 4},
        {"dept": "ITNU_CSE", "code": "MCA", "name": "Master of Computer Applications", "level": "PG", "semesters": 4},
        # ITNU ECE & EE
        {"dept": "ITNU_ECE", "code": "BEC", "name": "B.Tech in Electronics & Communication", "level": "UG", "semesters": 8},
        {"dept": "ITNU_ECE", "code": "MVL", "name": "M.Tech in VLSI Design", "level": "PG", "semesters": 4},
        {"dept": "ITNU_EE", "code": "BEE", "name": "B.Tech in Electrical Engineering", "level": "UG", "semesters": 8},
        {"dept": "ITNU_EE", "code": "MEP", "name": "M.Tech in Electrical Power Systems", "level": "PG", "semesters": 4},
        # ITNU ME & CL & CH & IC
        {"dept": "ITNU_ME", "code": "BME", "name": "B.Tech in Mechanical Engineering", "level": "UG", "semesters": 8},
        {"dept": "ITNU_ME", "code": "MME", "name": "M.Tech in Mechanical CAD/CAM", "level": "PG", "semesters": 4},
        {"dept": "ITNU_CL", "code": "BCL", "name": "B.Tech in Civil Engineering", "level": "UG", "semesters": 8},
        {"dept": "ITNU_CL", "code": "MCL", "name": "M.Tech in Construction Technology", "level": "PG", "semesters": 4},
        {"dept": "ITNU_CH", "code": "BCH", "name": "B.Tech in Chemical Engineering", "level": "UG", "semesters": 8},
        {"dept": "ITNU_IC", "code": "BIC", "name": "B.Tech in Instrumentation & Control", "level": "UG", "semesters": 8},
        # IMNU
        {"dept": "IMNU_DMS", "code": "MBA", "name": "Master of Business Administration", "level": "PG", "semesters": 4},
        {"dept": "IMNU_DMS", "code": "IBM", "name": "Integrated BBA-MBA (5-Year)", "level": "INTEGRATED", "semesters": 10},
        {"dept": "IMNU_DMS", "code": "BBA", "name": "Bachelor of Business Administration (Hons)", "level": "UG", "semesters": 6},
        # IPNU
        {"dept": "IPNU_DPS", "code": "BPH", "name": "Bachelor of Pharmacy (B.Pharm)", "level": "UG", "semesters": 8},
        {"dept": "IPNU_DPS", "code": "MPH", "name": "Master of Pharmacy (M.Pharm)", "level": "PG", "semesters": 4},
        # ISNU
        {"dept": "ISNU_DBS", "code": "MBT", "name": "M.Sc. in Biotechnology", "level": "PG", "semesters": 4},
        {"dept": "ISNU_DBS", "code": "MMB", "name": "M.Sc. in Microbiology", "level": "PG", "semesters": 4},
        {"dept": "ISNU_DCH", "code": "MCH", "name": "M.Sc. in Chemistry", "level": "PG", "semesters": 4},
        # ILNU
        {"dept": "ILNU_DOL", "code": "BAL", "name": "B.A. LL.B. (Hons)", "level": "UG", "semesters": 10},
        {"dept": "ILNU_DOL", "code": "BBL", "name": "B.B.A. LL.B. (Hons)", "level": "UG", "semesters": 10},
        {"dept": "ILNU_DOL", "code": "LLM", "name": "Master of Laws (LL.M.)", "level": "PG", "semesters": 2},
        # IAPNU
        {"dept": "IAPNU_DOA", "code": "BAR", "name": "Bachelor of Architecture (B.Arch)", "level": "UG", "semesters": 10},
        {"dept": "IAPNU_DOP", "code": "BPL", "name": "Bachelor of Planning (B.Plan)", "level": "UG", "semesters": 8},
        # ICNU
        {"dept": "ICNU_DOC", "code": "BCM", "name": "Bachelor of Commerce (B.Com Hons)", "level": "UG", "semesters": 6},
        # IDNU
        {"dept": "IDNU_DOD", "code": "BCD", "name": "B.Des in Communication Design", "level": "UG", "semesters": 8},
        {"dept": "IDNU_DOD", "code": "BID", "name": "B.Des in Industrial Design", "level": "UG", "semesters": 8},
        # FDSR
        {"dept": "FDSR_DSR", "code": "PHD", "name": "Doctor of Philosophy (Ph.D.)", "level": "DOCTORAL", "semesters": 6},
    ]

    prog_map: dict[str, AcademicProgram] = {}
    for p_data in ALL_PROGRAMS_CONFIG:
        parent_dept = dept_map.get(p_data["dept"])
        if not parent_dept:
            continue
        stmt = select(AcademicProgram).where(AcademicProgram.department_id == parent_dept.id, AcademicProgram.code == p_data["code"])
        existing_p = (await session.execute(stmt)).scalar_one_or_none()
        if not existing_p:
            prog = AcademicProgram(
                department_id=parent_dept.id,
                code=p_data["code"],
                name=p_data["name"],
                level=p_data["level"],
                duration_semesters=p_data["semesters"],
                is_active=True,
            )
            session.add(prog)
            await session.flush()
            prog_map[p_data["code"]] = prog
            logger.info("Seeded Program: %s (%s)", p_data["name"], p_data["code"])
        else:
            prog_map[p_data["code"]] = existing_p

    # E. Admission Batches & Divisions for Key Programs
    bce_prog = prog_map.get("BCE")
    batch = None
    divisions_map: dict[str, AcademicDivision] = {}
    if bce_prog:
        batch_stmt = select(AcademicBatch).where(AcademicBatch.program_id == bce_prog.id, AcademicBatch.admission_year == 2023)
        batch = (await session.execute(batch_stmt)).scalar_one_or_none()
        if not batch:
            batch = AcademicBatch(
                program_id=bce_prog.id,
                admission_year=2023,
                graduating_year=2027,
                name="Batch of 2023-2027",
                is_current=True,
            )
            session.add(batch)
            await session.flush()
            logger.info("Seeded Batch: %s", batch.name)

        # Divisions A, B and C
        for div_code in ["A", "B", "C"]:
            div_stmt = select(AcademicDivision).where(AcademicDivision.batch_id == batch.id, AcademicDivision.code == div_code)
            existing_div = (await session.execute(div_stmt)).scalar_one_or_none()
            if not existing_div:
                div = AcademicDivision(
                    batch_id=batch.id,
                    code=div_code,
                    name=f"Division {div_code}",
                    current_semester=6,
                    is_active=True,
                )
                session.add(div)
                await session.flush()
                divisions_map[div_code] = div
                logger.info("Seeded Division: %s", div.name)
            else:
                divisions_map[div_code] = existing_div

    # F. Seed Governance & Faculty Accounts Across Hierarchy Levels
    cse_dept = dept_map.get("ITNU_CSE")
    itnu = institutes_map.get("ITNU")

    GOVERNANCE_USERS = [
        {
            "email": "dean.it@nirmauni.ac.in",
            "name": "Dr. R. N. Patel (Dean, ITNU)",
            "role": "dean",
            "institute_id": itnu.id if itnu else None,
            "department_id": None,
            "institute_code": "ITNU",
            "department_code": None,
        },
        {
            "email": "hod.cse@nirmauni.ac.in",
            "name": "Dr. Madhuri Bhavsar (HOD, CSE)",
            "role": "hod",
            "institute_id": itnu.id if itnu else None,
            "department_id": cse_dept.id if cse_dept else None,
            "institute_code": "ITNU",
            "department_code": "CSE",
        },
        {
            "email": "operator@nirmauni.ac.in",
            "name": "Dr. Rajesh Patel (CSE Faculty)",
            "role": "operator",
            "institute_id": itnu.id if itnu else None,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": None,
            "division_id": None,
            "institute_code": "ITNU",
            "department_code": "CSE",
        },
        {
            "email": "coord.bce@nirmauni.ac.in",
            "name": "Prof. Priyank Patel (Program Coordinator, B.Tech CSE)",
            "role": "program_coordinator",
            "institute_id": itnu.id if itnu else None,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": prog_map.get("BCE").id if prog_map.get("BCE") else None,
            "division_id": None,
            "institute_code": "ITNU",
            "department_code": "CSE",
        },
        {
            "email": "cc.diva@nirmauni.ac.in",
            "name": "Prof. Swati Jain (Class Coordinator, Div A)",
            "role": "class_coordinator",
            "institute_id": itnu.id if itnu else None,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": prog_map.get("BCE").id if prog_map.get("BCE") else None,
            "division_id": divisions_map.get("A").id if divisions_map.get("A") else None,
            "institute_code": "ITNU",
            "department_code": "CSE",
        },
        {
            "email": "mentor.cse@nirmauni.ac.in",
            "name": "Prof. Amit Sharma (Faculty Mentor)",
            "role": "faculty_mentor",
            "institute_id": itnu.id if itnu else None,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": None,
            "division_id": None,
            "institute_code": "ITNU",
            "department_code": "CSE",
        },
    ]

    for u_info in GOVERNANCE_USERS:
        u_stmt = select(StaffUser).where(StaffUser.email == u_info["email"])
        existing_u = (await session.execute(u_stmt)).scalar_one_or_none()
        if not existing_u:
            new_u = StaffUser(
                email=u_info["email"],
                name=u_info["name"],
                role=u_info["role"],
                password_hash=pwd_context.hash("Nirma@123"),
                institute_id=u_info.get("institute_id"),
                department_id=u_info.get("department_id"),
                program_id=u_info.get("program_id"),
                division_id=u_info.get("division_id"),
                institute_code=u_info.get("institute_code"),
                department_code=u_info.get("department_code"),
                is_active=True,
            )
            session.add(new_u)
            await session.flush()
            logger.info("Seeded staff member: %s (%s)", u_info["email"], u_info["role"])
        else:
            existing_u.role = u_info["role"]
            existing_u.institute_id = u_info.get("institute_id")
            existing_u.department_id = u_info.get("department_id")
            existing_u.program_id = u_info.get("program_id")
            existing_u.division_id = u_info.get("division_id")
            existing_u.institute_code = u_info.get("institute_code")
            existing_u.department_code = u_info.get("department_code")
            session.add(existing_u)

    # G. Seed Sample Students with Real Taxonomy and Department Scoping
    div_a = divisions_map.get("A")
    div_b = divisions_map.get("B")
    SAMPLE_STUDENTS = [
        {
            "roll": "23BCE045",
            "name": "Aarav Patel",
            "phone": "+919876500001",
            "department": "Computer Science & Engineering",
            "semester": 6,
            "institute_id": itnu.id,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": prog_map.get("BCE").id if prog_map.get("BCE") else None,
            "batch_id": batch.id if batch else None,
            "division_id": div_a.id if div_a else None,
            "lab_batch": "A2",
            "attendance_pct": 68.50,
            "pending_fee_inr": 0.00,
            "language_pref": "gu",
        },
        {
            "roll": "23BCE112",
            "name": "Diya Shah",
            "phone": "+919876500002",
            "department": "Computer Science & Engineering",
            "semester": 6,
            "institute_id": itnu.id,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": prog_map.get("BCE").id if prog_map.get("BCE") else None,
            "batch_id": batch.id if batch else None,
            "division_id": div_b.id if div_b else None,
            "lab_batch": "B1",
            "attendance_pct": 84.00,
            "pending_fee_inr": 45000.00,
            "language_pref": "hi",
        },
        {
            "roll": "23BAI012",
            "name": "Rohan Mehta",
            "phone": "+919876500003",
            "department": "Computer Science & Engineering",
            "semester": 6,
            "institute_id": itnu.id,
            "department_id": cse_dept.id if cse_dept else None,
            "program_id": prog_map.get("BAI").id if prog_map.get("BAI") else None,
            "batch_id": batch.id if batch else None,
            "division_id": div_a.id if div_a else None,
            "lab_batch": "A1",
            "attendance_pct": 92.00,
            "pending_fee_inr": 0.00,
            "language_pref": "en",
        },
        {
            "roll": "23BME019",
            "name": "Kavya Sharma",
            "phone": "+919876500004",
            "department": "Mechanical Engineering",
            "semester": 6,
            "institute_id": itnu.id,
            "department_id": dept_map.get("ME").id if dept_map.get("ME") else None,
            "program_id": None,
            "batch_id": None,
            "division_id": None,
            "lab_batch": None,
            "attendance_pct": 72.00,
            "pending_fee_inr": 12000.00,
            "language_pref": "hi",
        },
        {
            "roll": "23MBA005",
            "name": "Ananya Desai",
            "phone": "+919876500005",
            "department": "Institute of Management",
            "semester": 4,
            "institute_id": institutes_map.get("IMNU").id if institutes_map.get("IMNU") else None,
            "department_id": None,
            "program_id": None,
            "batch_id": None,
            "division_id": None,
            "lab_batch": None,
            "attendance_pct": 95.00,
            "pending_fee_inr": 0.00,
            "language_pref": "en",
        },
    ]

    for s_data in SAMPLE_STUDENTS:
        s_stmt = select(Student).where(Student.roll_number == s_data["roll"])
        existing_s = (await session.execute(s_stmt)).scalar_one_or_none()
        if not existing_s:
            student = Student(
                roll_number=s_data["roll"],
                name=s_data["name"],
                phone=s_data["phone"],
                department=s_data["department"],
                semester=s_data["semester"],
                institute_id=s_data["institute_id"],
                department_id=s_data["department_id"],
                program_id=s_data["program_id"],
                batch_id=s_data["batch_id"],
                division_id=s_data["division_id"],
                lab_batch=s_data["lab_batch"],
                attendance_pct=s_data["attendance_pct"],
                pending_fee_inr=s_data["pending_fee_inr"],
                language_pref=s_data["language_pref"],
                is_active=True,
            )
            session.add(student)
            logger.info("Seeded Student: %s (%s)", s_data["name"], s_data["roll"])
        else:
            existing_s.institute_id = s_data["institute_id"]
            existing_s.department_id = s_data["department_id"]
            existing_s.program_id = s_data["program_id"]
            existing_s.batch_id = s_data["batch_id"]
            existing_s.division_id = s_data["division_id"]
            existing_s.lab_batch = s_data["lab_batch"]
            existing_s.attendance_pct = s_data["attendance_pct"]
            existing_s.pending_fee_inr = s_data["pending_fee_inr"]
            session.add(existing_s)


async def main() -> None:
    """Entry point for database schema generation and initial seeding."""
    logger.info("Connecting to database: %s", settings.database_url)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created.")

    async with async_session_factory() as session:
        await seed_data(session)


if __name__ == "__main__":
    asyncio.run(main())
