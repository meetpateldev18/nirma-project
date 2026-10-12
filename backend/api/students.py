"""
Student Lookup API Router — Search for an Individual Call Recipient.

Provides the search endpoint behind the "call one person" flow: staff type a name,
roll number, or phone number and pick the right student instead of only ever targeting
a department/semester batch.

Endpoints:
    - GET /api/students/search: Name/roll/phone search, capped to a handful of matches.

Dependencies:
    - fastapi >= 0.111
    - sqlalchemy >= 2.0
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.database.models import StaffUser, Student
from backend.database.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/students", tags=["Students"])


class StudentSearchResult(BaseModel):
    """Minimal student identity fields needed to pick a single call recipient."""

    id: int
    name: str
    roll_number: str
    phone: str
    department: Optional[str]
    semester: Optional[int]


@router.get("/search", response_model=List[StudentSearchResult])
async def search_students(
    q: str = Query(..., min_length=2, max_length=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: StaffUser = Depends(get_current_user),
) -> List[StudentSearchResult]:
    """Matches active students by name, roll number, or phone (case-insensitive, partial)."""
    term = f"%{q.strip()}%"
    stmt = (
        select(Student)
        .where(
            Student.is_active.is_(True),
            or_(
                Student.name.ilike(term),
                Student.roll_number.ilike(term),
                Student.phone.ilike(term),
            ),
        )
        .order_by(Student.name)
        .limit(10)
    )
    res = await session.execute(stmt)
    students = res.scalars().all()
    return [StudentSearchResult.model_validate(s, from_attributes=True) for s in students]
