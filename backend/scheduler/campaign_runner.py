"""
Campaign Runner Module — Student Batching & Call Task Generation.

This module resolves target recipient filters for a scheduled campaign,
queries matching student records, enforces role-based departmental scoping,
and populates individual CallTask records in PostgreSQL ready for carrier dispatch.

Dependencies:
    - sqlalchemy >= 2.0
"""

import logging
from typing import Any, Dict, List
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database.models import AcademicAuditLog, CallCampaign, CallTask, StaffUser, Student

logger = logging.getLogger(__name__)


class CampaignRunner:
    """
    Orchestrator for creating CallTask batches from CallCampaign criteria.
    """

    @staticmethod
    def generate_tasks_for_campaign(campaign_id: int, db: Session) -> int:
        """
        Resolves a campaign's student filter criteria and generates CallTask rows.

        Enforces multi-tenant scoping: if the creator of the campaign is a faculty
        member (role != 'admin'), student matching is strictly clamped to their
        assigned academic department or constituent institute.

        Args:
            campaign_id: Primary key of the CallCampaign.
            db: Synchronous database session.

        Returns:
            int: Number of generated CallTask records.
        """
        campaign = db.query(CallCampaign).filter(CallCampaign.id == campaign_id).first()
        if not campaign:
            logger.error("Campaign ID %d not found.", campaign_id)
            return 0

        # Parse target filter criteria
        filters: Dict[str, Any] = campaign.target_filter or {}
        query = db.query(Student).filter(Student.is_active == True)  # noqa: E712

        # Multi-Tenant Attribute-Based Access Control (ABAC) Scope Enforcement
        creator = None
        if campaign.created_by:
            creator = db.query(StaffUser).filter(StaffUser.id == campaign.created_by).first()
            if creator and creator.role not in ("admin", "super_admin"):
                if creator.role == "dean":
                    if creator.institute_id:
                        query = query.filter(Student.institute_id == creator.institute_id)
                elif creator.role in ("hod", "operator"):
                    if creator.department_id:
                        dept_conditions = [Student.department_id == creator.department_id]
                        if creator.department_code:
                            dept_conditions.append(Student.department.ilike(f"%{creator.department_code}%"))
                        query = query.filter(or_(*dept_conditions))
                    elif creator.institute_id:
                        query = query.filter(Student.institute_id == creator.institute_id)
                elif creator.role == "program_coordinator":
                    if creator.program_id:
                        query = query.filter(Student.program_id == creator.program_id)
                    elif creator.department_id:
                        query = query.filter(Student.department_id == creator.department_id)
                elif creator.role == "class_coordinator":
                    if creator.division_id:
                        query = query.filter(Student.division_id == creator.division_id)
                    elif creator.department_id:
                        query = query.filter(Student.department_id == creator.department_id)
                elif creator.role == "faculty_mentor":
                    query = query.filter(Student.mentor_id == creator.id)

        # Individual-call shortcut: a single named recipient bypasses group filters
        if "student_id" in filters and filters["student_id"]:
            query = query.filter(Student.id == int(filters["student_id"]))
        else:
            # Academic Hierarchy Cascading Filters
            if "institute_id" in filters and filters["institute_id"]:
                query = query.filter(Student.institute_id == int(filters["institute_id"]))
            if "department_id" in filters and filters["department_id"]:
                query = query.filter(Student.department_id == int(filters["department_id"]))
            if "program_id" in filters and filters["program_id"]:
                query = query.filter(Student.program_id == int(filters["program_id"]))
            if "batch_id" in filters and filters["batch_id"]:
                query = query.filter(Student.batch_id == int(filters["batch_id"]))
            if "division_id" in filters and filters["division_id"]:
                query = query.filter(Student.division_id == int(filters["division_id"]))
            if "lab_batch" in filters and filters["lab_batch"]:
                query = query.filter(Student.lab_batch == str(filters["lab_batch"]))

            # Standing & Operational Criteria Filters
            if "max_attendance" in filters and filters["max_attendance"] is not None:
                query = query.filter(Student.attendance_pct <= float(filters["max_attendance"]))
            if "min_fee" in filters and filters["min_fee"] is not None:
                query = query.filter(Student.pending_fee_inr >= float(filters["min_fee"]))
            if filters.get("has_pending_fee"):
                query = query.filter(Student.pending_fee_inr > 0)

            # Legacy department / semester / language filter backwards compatibility
            if "department" in filters and filters["department"] and "department_id" not in filters:
                query = query.filter(Student.department == filters["department"])
            if "semester" in filters and filters["semester"]:
                query = query.filter(Student.semester == int(filters["semester"]))
            if "language_pref" in filters and filters["language_pref"]:
                query = query.filter(Student.language_pref == filters["language_pref"])

        matching_students: List[Student] = query.all()
        logger.info(
            "Campaign ID %d ('%s') matched %d active students.",
            campaign_id,
            campaign.name,
            len(matching_students),
        )

        generated_count = 0
        for student in matching_students:
            # Check if task already exists for this student in this campaign
            existing_task = (
                db.query(CallTask)
                .filter(
                    CallTask.campaign_id == campaign_id,
                    CallTask.student_id == student.id,
                )
                .first()
            )

            if not existing_task:
                task = CallTask(
                    campaign_id=campaign_id,
                    student_id=student.id,
                    student_phone=student.phone,
                    script_id=campaign.script_id,
                    status="pending",
                    retry_count=0,
                    scheduled_at=campaign.scheduled_at,
                )
                db.add(task)
                generated_count += 1

        campaign.status = "running" if generated_count > 0 else "completed"

        # Record Immutable Academic Audit Ledger Entry
        if creator:
            audit = AcademicAuditLog(
                action="campaign_dispatched",
                staff_id=creator.id,
                staff_email=creator.email,
                staff_role=creator.role,
                institute_code=creator.institute_code,
                department_code=creator.department_code,
                target_count=generated_count,
                target_filter=filters,
                campaign_id=campaign_id,
            )
            db.add(audit)

        db.commit()

        logger.info("Generated %d CallTask records for Campaign ID %d.", generated_count, campaign_id)
        return generated_count
