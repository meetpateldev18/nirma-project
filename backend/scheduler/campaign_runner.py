"""
Campaign Runner Module — Student Batching & Call Task Generation.

This module resolves target recipient filters for a scheduled campaign,
queries matching student records, and populates individual CallTask records
in PostgreSQL ready for Celery Beat dispatching.

Dependencies:
    - sqlalchemy >= 2.0
"""

import logging
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.database.models import CallCampaign, CallTask, Student

logger = logging.getLogger(__name__)


class CampaignRunner:
    """
    Orchestrator for creating CallTask batches from CallCampaign criteria.
    """

    @staticmethod
    def generate_tasks_for_campaign(campaign_id: int, db: Session) -> int:
        """
        Resolves a campaign's student filter criteria and generates CallTask rows.

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

        # Individual-call shortcut: a single named recipient bypasses every other filter.
        if "student_id" in filters and filters["student_id"]:
            query = query.filter(Student.id == int(filters["student_id"]))
        else:
            if "department" in filters and filters["department"]:
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
        db.commit()

        logger.info("Generated %d CallTask records for Campaign ID %d.", generated_count, campaign_id)
        return generated_count
