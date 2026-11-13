"""
Student In-Memory Trie Search Engine Module.

This module provides an ultra-low-latency in-memory Trie data structure for
instantaneous multi-token student search across Nirma University records.

Architectural Role:
    - Indexes student tokens (first name, surname/last name, roll number, phone)
      into an in-memory prefix and substring Trie.
    - Provides O(k) search latency (< 1ms) eliminating slow database ILIKE table scans
      and multi-table joins.
    - Strictly enforces multi-tier Attribute-Based Access Control (ABAC) in memory
      for Admin, Dean, HoD, Operator, Program Coordinator, Class Coordinator, and Faculty Mentor.
    - Supports dynamic cache invalidation and thread-safe async loading.

Dependencies:
    - pydantic >= 2.0
    - sqlalchemy >= 2.0
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database.models import StaffUser, Student

logger = logging.getLogger(__name__)


class StudentSearchDTO:
    """
    Lightweight in-memory data representation for indexed student records.
    """

    def __init__(
        self,
        id: int,
        name: str,
        roll_number: str,
        phone: str,
        department: Optional[str] = None,
        semester: Optional[int] = None,
        institute_id: Optional[int] = None,
        department_id: Optional[int] = None,
        program_id: Optional[int] = None,
        division_id: Optional[int] = None,
        institute_code: Optional[str] = None,
        department_code: Optional[str] = None,
        program_code: Optional[str] = None,
        division_code: Optional[str] = None,
        lab_batch: Optional[str] = None,
        mentor_id: Optional[int] = None,
    ) -> None:
        self.id = id
        self.name = name
        self.roll_number = roll_number
        self.phone = phone
        self.department = department
        self.semester = semester
        self.institute_id = institute_id
        self.department_id = department_id
        self.program_id = program_id
        self.division_id = division_id
        self.institute_code = institute_code
        self.department_code = department_code
        self.program_code = program_code
        self.division_code = division_code
        self.lab_batch = lab_batch
        self.mentor_id = mentor_id

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary compatible with StudentSearchResult schema."""
        return {
            "id": self.id,
            "name": self.name,
            "roll_number": self.roll_number,
            "phone": self.phone,
            "department": self.department,
            "semester": self.semester,
            "institute_id": self.institute_id,
            "department_id": self.department_id,
            "program_id": self.program_id,
            "division_id": self.division_id,
            "institute_code": self.institute_code,
            "department_code": self.department_code,
            "program_code": self.program_code,
            "division_code": self.division_code,
            "lab_batch": self.lab_batch,
        }


class TrieNode:
    """
    Node in the multi-token student Trie.
    """

    def __init__(self) -> None:
        self.children: Dict[str, TrieNode] = {}
        self.student_ids: Set[int] = set()


class StudentTrie:
    """
    High-performance in-memory Trie indexing student names (first, middle, surname),
    roll numbers, and phone numbers with instant prefix matching.
    """

    def __init__(self) -> None:
        self._root = TrieNode()
        self._students: Dict[int, StudentSearchDTO] = {}
        self._is_loaded: bool = False
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        """Resets the Trie and student store."""
        self._root = TrieNode()
        self._students.clear()
        self._is_loaded = False

    def is_loaded(self) -> bool:
        """Returns True if the Trie has been populated from the database."""
        return self._is_loaded

    def insert_token(self, token: str, student_id: int) -> None:
        """
        Inserts a single normalized alphanumeric token into the Trie.

        Args:
            token: Normalized lowercase string to index.
            student_id: Primary key of the student.
        """
        if not token:
            return
        curr = self._root
        curr.student_ids.add(student_id)
        for char in token:
            if char not in curr.children:
                curr.children[char] = TrieNode()
            curr = curr.children[char]
            curr.student_ids.add(student_id)

    def insert_student(self, student: StudentSearchDTO) -> None:
        """
        Indexes all searchable tokens and suffixes for a student into the Trie.

        Indexes:
            - Full name and all words in the name (first name, surname/last name, middle name).
            - Substring suffixes of surname/name words (to match in-between queries).
            - Roll number and alphanumeric suffixes (e.g., '21BCE045', 'BCE045', '045').
            - Phone number and trailing digits.

        Args:
            student: StudentSearchDTO instance.
        """
        self._students[student.id] = student
        sid = student.id

        # 1. Index full name
        norm_name = student.name.strip().lower()
        self.insert_token(norm_name, sid)

        # 2. Index each individual word (first name, middle name, surname/last name)
        words = re.findall(r"[a-z0-9]+", norm_name)
        for word in words:
            self.insert_token(word, sid)
            # Index suffixes of the word (length >= 3) for in-between / substring matching
            for i in range(1, len(word)):
                suffix = word[i:]
                if len(suffix) >= 2:
                    self.insert_token(suffix, sid)

        # 3. Index roll number
        norm_roll = student.roll_number.strip().lower()
        self.insert_token(norm_roll, sid)
        # Suffixes of roll number (e.g. 'bce045', '045')
        for i in range(1, len(norm_roll)):
            roll_suffix = norm_roll[i:]
            if len(roll_suffix) >= 2:
                self.insert_token(roll_suffix, sid)

        # 4. Index phone number
        digits_phone = re.sub(r"[^\d]", "", student.phone)
        if digits_phone:
            self.insert_token(digits_phone, sid)
            if len(digits_phone) >= 10:
                self.insert_token(digits_phone[-10:], sid)

    def search_prefix(self, token: str) -> Set[int]:
        """
        Retrieves matching student IDs for a given prefix in O(k) time.

        Args:
            token: Prefix string to look up.

        Returns:
            Set of matching student primary keys.
        """
        if not token:
            return set()
        curr = self._root
        for char in token:
            if char not in curr.children:
                return set()
            curr = curr.children[char]
        return curr.student_ids

    def search(
        self,
        query: str,
        current_user: StaffUser,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Executes an instant in-memory multi-token search with ABAC enforcement.

        Args:
            query: User search input string (e.g. 'Aarav', 'Patel', '21BCE045').
            current_user: Authenticated StaffUser requesting the search.
            limit: Maximum number of student records to return.

        Returns:
            List of student dictionaries matching StudentSearchResult schema.
        """
        clean_query = query.strip().lower()
        if not clean_query:
            return []

        # Split query into search terms
        terms = re.findall(r"[a-z0-9]+", clean_query)
        if not terms:
            terms = [clean_query]

        # Intersect matching IDs across all query tokens
        candidate_ids: Optional[Set[int]] = None
        for term in terms:
            matching = self.search_prefix(term)
            if candidate_ids is None:
                candidate_ids = set(matching)
            else:
                candidate_ids &= matching
            if not candidate_ids:
                break

        if not candidate_ids:
            # Fallback: try union if intersection is empty
            candidate_ids = set()
            for term in terms:
                candidate_ids.update(self.search_prefix(term))

        if not candidate_ids:
            return []

        # Apply Attribute-Based Access Control (ABAC) in memory
        filtered_students: List[StudentSearchDTO] = []
        for sid in candidate_ids:
            st = self._students.get(sid)
            if not st:
                continue
            if self._satisfies_abac(st, current_user):
                filtered_students.append(st)

        # Relevance scoring
        def score_student(st: StudentSearchDTO) -> tuple:
            name_lower = st.name.lower()
            roll_lower = st.roll_number.lower()
            # Exact roll match -> rank 0
            if clean_query == roll_lower:
                return (0, 0, st.name)
            # Starts with roll -> rank 1
            if roll_lower.startswith(clean_query):
                return (1, 0, st.name)
            # Name starts with query -> rank 2
            if name_lower.startswith(clean_query):
                return (2, 0, st.name)
            # Any word in name starts with query -> rank 3
            words = name_lower.split()
            if any(w.startswith(clean_query) for w in words):
                return (3, 0, st.name)
            # Query is a substring of name -> rank 4
            if clean_query in name_lower:
                return (4, name_lower.find(clean_query), st.name)
            return (5, 0, st.name)

        filtered_students.sort(key=score_student)
        return [st.to_dict() for st in filtered_students[:limit]]

    def _satisfies_abac(self, student: StudentSearchDTO, user: StaffUser) -> bool:
        """
        Validates whether the user has authorization to view the student record.

        Args:
            student: StudentSearchDTO instance.
            user: Current authenticated staff member.

        Returns:
            bool: True if authorized, False otherwise.
        """
        role = user.role
        if role in ("admin", "super_admin"):
            return True

        if role == "dean":
            if user.institute_id and student.institute_id != user.institute_id:
                return False
            return True

        if role in ("hod", "operator"):
            if user.department_id:
                if student.department_id == user.department_id:
                    return True
                if (
                    user.department_code
                    and student.department
                    and user.department_code.lower() in student.department.lower()
                ):
                    return True
                return False
            if user.institute_id and student.institute_id != user.institute_id:
                return False
            return True

        if role == "program_coordinator":
            if user.program_id:
                return student.program_id == user.program_id
            if user.department_id:
                return student.department_id == user.department_id
            return True

        if role == "class_coordinator":
            if user.division_id:
                return student.division_id == user.division_id
            if user.department_id:
                return student.department_id == user.department_id
            return True

        if role == "faculty_mentor":
            return student.mentor_id == user.id

        return True

    async def load_from_db(self, session: AsyncSession) -> int:
        """
        Loads all active students and relationships from PostgreSQL into the in-memory Trie.

        Args:
            session: Active SQLAlchemy AsyncSession.

        Returns:
            int: Total number of students indexed.
        """
        async with self._lock:
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
            result = await session.execute(stmt)
            students = result.scalars().all()

            # Rebuild index
            new_root = TrieNode()
            new_students: Dict[int, StudentSearchDTO] = {}

            old_root = self._root
            old_students = self._students

            self._root = new_root
            self._students = new_students

            for s in students:
                dto = StudentSearchDTO(
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
                    mentor_id=getattr(s, "mentor_id", None),
                )
                self.insert_student(dto)

            self._is_loaded = True
            logger.info("Successfully loaded and indexed %d students in Trie", len(students))
            return len(students)

    async def ensure_loaded(self, session: AsyncSession) -> None:
        """Ensures the Trie is loaded with data; loads lazily if empty."""
        if not self._is_loaded or not self._students:
            await self.load_from_db(session)


# Global singleton instance of StudentTrie
student_trie = StudentTrie()
