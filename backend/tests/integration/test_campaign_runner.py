"""
Integration Tests — Campaign Runner, Student Target Filtering & Task Generation.

Tests `backend.scheduler.campaign_runner.CampaignRunner`:
- Complex target filter evaluation (department, semester, language_pref).
- Exclusion of inactive student accounts.
- Task generation idempotency (never generating duplicate tasks on re-run).
- Campaign status state transition ('running' if tasks generated, 'completed' if empty).
"""

import pytest
from sqlalchemy.orm import Session

from backend.database.models import CallCampaign, CallScript, CallTask, Student, utc_now
from backend.scheduler.campaign_runner import CampaignRunner


def test_campaign_runner_department_and_active_filtering(sync_db_session: Session):
    """
    Verifies that CampaignRunner filters by department and strictly excludes
    inactive students even if department matches.
    """
    # 1. Seed Script
    script = CallScript(
        name="Fee Script",
        category="fee_reminder",
        language="hi",
        system_prompt="prompt",
        opening_message="hello",
    )
    sync_db_session.add(script)
    sync_db_session.commit()

    # 2. Seed Students: 2 Active CS, 1 Inactive CS, 1 Active ME
    s1 = Student(roll_number="CS_001", name="Active CS 1", phone="+9198765001", department="CS", semester=4, is_active=True)
    s2 = Student(roll_number="CS_002", name="Active CS 2", phone="+9198765002", department="CS", semester=4, is_active=True)
    s3 = Student(roll_number="CS_003", name="Inactive CS", phone="+9198765003", department="CS", semester=4, is_active=False)
    s4 = Student(roll_number="ME_001", name="Active ME", phone="+9198765004", department="ME", semester=4, is_active=True)
    sync_db_session.add_all([s1, s2, s3, s4])
    sync_db_session.commit()

    # 3. Create Campaign targeting CS department
    campaign = CallCampaign(
        name="CS Fee Reminder",
        script_id=script.id,
        target_filter={"department": "CS"},
        scheduled_at=utc_now(),
        status="pending",
    )
    sync_db_session.add(campaign)
    sync_db_session.commit()

    # 4. Run Task Generation
    generated_count = CampaignRunner.generate_tasks_for_campaign(campaign.id, sync_db_session)

    assert generated_count == 2
    sync_db_session.refresh(campaign)
    assert campaign.status == "running"

    # Verify tasks in database
    tasks = sync_db_session.query(CallTask).filter(CallTask.campaign_id == campaign.id).all()
    assert len(tasks) == 2
    phones = {t.student_phone for t in tasks}
    assert phones == {"+9198765001", "+9198765002"}


def test_campaign_runner_idempotency_no_duplicate_tasks(sync_db_session: Session):
    """
    Verifies that executing CampaignRunner multiple times on the same campaign
    is strictly idempotent and does not create duplicate CallTask records.
    """
    script = CallScript(name="Script", category="cat", language="hi", system_prompt="p", opening_message="o")
    sync_db_session.add(script)
    sync_db_session.commit()

    student = Student(roll_number="IDEMP_01", name="Student", phone="+9198765011", department="IT", is_active=True)
    sync_db_session.add(student)
    sync_db_session.commit()

    campaign = CallCampaign(
        name="Idempotent Campaign",
        script_id=script.id,
        target_filter={"department": "IT"},
        scheduled_at=utc_now(),
        status="pending",
    )
    sync_db_session.add(campaign)
    sync_db_session.commit()

    # First run generates 1 task
    count1 = CampaignRunner.generate_tasks_for_campaign(campaign.id, sync_db_session)
    assert count1 == 1

    # Second run should generate 0 tasks (already exists)
    count2 = CampaignRunner.generate_tasks_for_campaign(campaign.id, sync_db_session)
    assert count2 == 0

    total_tasks = (
        sync_db_session.query(CallTask)
        .filter(CallTask.campaign_id == campaign.id)
        .count()
    )
    assert total_tasks == 1


def test_campaign_runner_zero_matches_sets_status_completed(sync_db_session: Session):
    """
    Verifies that if no active students match the campaign criteria,
    the campaign status is marked as 'completed' and 0 tasks are returned.
    """
    script = CallScript(name="Script", category="cat", language="hi", system_prompt="p", opening_message="o")
    sync_db_session.add(script)
    sync_db_session.commit()

    campaign = CallCampaign(
        name="Empty Campaign",
        script_id=script.id,
        target_filter={"department": "CIVIL_NONEXISTENT"},
        scheduled_at=utc_now(),
        status="pending",
    )
    sync_db_session.add(campaign)
    sync_db_session.commit()

    generated_count = CampaignRunner.generate_tasks_for_campaign(campaign.id, sync_db_session)
    assert generated_count == 0

    sync_db_session.refresh(campaign)
    assert campaign.status == "completed"


def test_campaign_runner_invalid_campaign_returns_zero(sync_db_session: Session):
    """Verifies that attempting task generation for a non-existent campaign safely returns 0."""
    result = CampaignRunner.generate_tasks_for_campaign(999999, sync_db_session)
    assert result == 0


def test_campaign_runner_creator_department_scoping(sync_db_session: Session):
    """
    Verifies that when an operator/faculty member creates a campaign,
    the generated tasks are strictly clamped to their assigned department,
    preventing cross-department calling even if target_filter has no department restriction.
    """
    from backend.database.models import StaffUser, Department, Institute

    # Create faculty user scoped to CSE (dept_id = 101)
    dept = Department(institute_id=1, code="CSE", name="Computer Science", is_active=True)
    sync_db_session.add(dept)
    sync_db_session.flush()

    faculty = StaffUser(
        email="faculty.cse@nirmauni.ac.in",
        name="CSE Faculty",
        role="operator",
        password_hash="fakehash",
        department_id=dept.id,
        department_code="CSE",
        is_active=True,
    )
    sync_db_session.add(faculty)
    sync_db_session.flush()

    script = CallScript(name="Faculty Script", category="general", language="en", system_prompt="p", opening_message="o")
    sync_db_session.add(script)
    sync_db_session.flush()

    # Seed 1 CSE student and 1 Mechanical student
    s_cse = Student(
        roll_number="SCOPED_CSE_01",
        name="CSE Student",
        phone="+919876509901",
        department_id=dept.id,
        department="Computer Science",
        is_active=True,
    )
    s_me = Student(
        roll_number="SCOPED_ME_01",
        name="ME Student",
        phone="+919876509902",
        department_id=999,
        department="Mechanical",
        is_active=True,
    )
    sync_db_session.add_all([s_cse, s_me])
    sync_db_session.commit()

    # Campaign created by CSE faculty with an open filter (no department specified)
    campaign = CallCampaign(
        name="Open Scope Announcement",
        script_id=script.id,
        target_filter={},
        scheduled_at=utc_now(),
        status="pending",
        created_by=faculty.id,
    )
    sync_db_session.add(campaign)
    sync_db_session.commit()

    # Run generator — should only generate 1 task for the CSE student, NOT the ME student!
    count = CampaignRunner.generate_tasks_for_campaign(campaign.id, sync_db_session)
    assert count == 1

    tasks = sync_db_session.query(CallTask).filter(CallTask.campaign_id == campaign.id).all()
    assert len(tasks) == 1
    assert tasks[0].student_id == s_cse.id

