"""
Database Models Module — SQLAlchemy 2.0 Declarative ORM Schemas.

This module defines the relational database models for the Nirma Calling Assistant.
It tracks students, staff users, reusable call scripts, outbound campaigns,
individual execution tasks, and complete conversation transcripts.

Design Invariants:
    - SQLAlchemy 2.0 typed mappings (Mapped, mapped_column)
    - UTC timestamps with timezone support
    - Optimized compound and single-column indices for high-throughput polling
    - JSONB fields for unstructured filters, error logs, and conversational turns

Dependencies:
    - sqlalchemy >= 2.0
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models in the application."""
    pass


class StaffUser(Base):
    """
    Staff and administrative portal users with role-based access control.

    Attributes:
        id: Primary key surrogate identifier.
        email: Unique institutional email address (e.g. 'operator@nirmauni.ac.in').
        name: Full human name of the staff member.
        role: Security clearance role ('admin' or 'operator').
        password_hash: Bcrypt cryptographic password hash.
        is_active: Status flag indicating whether the account is enabled.
        created_at: Account creation timestamp.
    """

    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="operator", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    created_scripts: Mapped[List["CallScript"]] = relationship(
        "CallScript", back_populates="creator"
    )
    created_campaigns: Mapped[List["CallCampaign"]] = relationship(
        "CallCampaign", back_populates="creator"
    )

    def __repr__(self) -> str:
        return f"<StaffUser(id={self.id}, email='{self.email}', role='{self.role}')>"


class Student(Base):
    """
    Student profile information, contact details, and language preferences.

    Attributes:
        id: Primary key identifier.
        roll_number: Unique university roll number (e.g. '21BCE001').
        name: Full student name.
        phone: Primary E.164 phone number.
        alt_phone: Secondary/parent emergency phone number.
        language_pref: Preferred language code ('hi', 'gu', 'en').
        department: Academic department (e.g. 'Computer Science & Engineering').
        semester: Current academic semester (1-8).
        whatsapp_number: Optional phone number for automated WhatsApp follow-ups.
        is_active: Status flag indicating whether student is currently enrolled.
        created_at: Record creation timestamp.
        updated_at: Record last modification timestamp.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roll_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    alt_phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    language_pref: Mapped[str] = mapped_column(String(10), default="hi", nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    semester: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    call_tasks: Mapped[List["CallTask"]] = relationship("CallTask", back_populates="student")

    __table_args__ = (
        Index("idx_students_phone", "phone"),
        Index("idx_students_dept_sem_active", "department", "semester", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Student(id={self.id}, roll='{self.roll_number}', name='{self.name}')>"


class CallScript(Base):
    """
    Structured call templates containing system prompts and initial greetings.

    Attributes:
        id: Primary key identifier.
        name: Descriptive script name (e.g. 'Semester Fee Reminder — Hindi').
        category: Purpose category ('fee_reminder', 'exam_notice', 'attendance_alert', etc.).
        language: Language ISO code ('hi', 'gu', 'en').
        system_prompt: Core LLM instructions and persona guidelines.
        opening_message: Initial synthesized greeting spoken when caller answers.
        is_active: Status flag for template usability.
        created_by: Staff user ID who authored the script template.
        created_at: Template creation timestamp.
    """

    __tablename__ = "call_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    opening_message: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    creator: Mapped[Optional["StaffUser"]] = relationship(
        "StaffUser", back_populates="created_scripts"
    )
    campaigns: Mapped[List["CallCampaign"]] = relationship(
        "CallCampaign", back_populates="script"
    )

    __table_args__ = (
        Index("idx_call_scripts_created_by", "created_by"),
    )

    def __repr__(self) -> str:
        return f"<CallScript(id={self.id}, name='{self.name}', category='{self.category}')>"


class CallCampaign(Base):
    """
    Batch outbound call campaigns scheduled by college administrators.

    Attributes:
        id: Primary key identifier.
        name: Campaign name (e.g. 'BTech 2026 Fee Reminder Round 1').
        script_id: Foreign key to the active call script template.
        target_filter: JSONB criteria used to select recipients (e.g. {'department': 'CS'}).
        scheduled_at: Target UTC datetime when the campaign should begin dialing.
        max_retries: Maximum number of retry attempts for unanswered calls.
        retry_delay_min: Interval in minutes before attempting an unanswered call retry.
        status: Campaign execution status ('pending', 'running', 'completed', 'cancelled').
        created_by: Staff user ID who launched the campaign.
        created_at: Campaign creation timestamp.
    """

    __tablename__ = "call_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    script_id: Mapped[int] = mapped_column(Integer, ForeignKey("call_scripts.id"), nullable=False)
    target_filter: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    retry_delay_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("staff_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    script: Mapped["CallScript"] = relationship("CallScript", back_populates="campaigns")
    creator: Mapped[Optional["StaffUser"]] = relationship(
        "StaffUser", back_populates="created_campaigns"
    )
    tasks: Mapped[List["CallTask"]] = relationship("CallTask", back_populates="campaign")

    __table_args__ = (
        Index("idx_call_campaigns_script_id", "script_id"),
        Index("idx_call_campaigns_created_by", "created_by"),
    )

    def __repr__(self) -> str:
        return f"<CallCampaign(id={self.id}, name='{self.name}', status='{self.status}')>"


class CallTask(Base):
    """
    Individual outbound phone call dispatched to a specific student recipient.

    Attributes:
        id: Primary key identifier.
        campaign_id: Foreign key referencing the parent campaign.
        student_id: Foreign key referencing the target student.
        student_phone: Sanitized recipient phone number at call creation time.
        script_id: Foreign key referencing the script used for this call.
        status: Real-time call state ('pending', 'ringing', 'in_progress', etc.).
        plivo_uuid: Unique call/request UUID assigned by the Plivo carrier.
        retry_count: Number of times this task has been retried due to no-answer.
        scheduled_at: Time when this specific call is eligible for dispatch.
        placed_at: Timestamp when carrier API was requested to initiate call.
        answered_at: Timestamp when recipient picked up the phone.
        ended_at: Timestamp when call was disconnected.
        duration_sec: Total connected call duration in seconds.
        outcome: Final disposition ('completed', 'no_answer', 'busy', 'failed', 'voicemail').
        created_at: Task creation timestamp.
    """

    __tablename__ = "call_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_campaigns.id"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id"), nullable=False, index=True
    )
    student_phone: Mapped[str] = mapped_column(String(15), nullable=False)
    script_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_scripts.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    plivo_uuid: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    placed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    campaign: Mapped["CallCampaign"] = relationship("CallCampaign", back_populates="tasks")
    student: Mapped["Student"] = relationship("Student", back_populates="call_tasks")
    script: Mapped["CallScript"] = relationship("CallScript")
    log: Mapped[Optional["CallLog"]] = relationship(
        "CallLog", back_populates="task", uselist=False
    )

    __table_args__ = (
        Index("idx_call_tasks_status", "status"),
        Index("idx_call_tasks_campaign", "campaign_id"),
        Index("idx_call_tasks_scheduled", "scheduled_at"),
        Index("idx_call_tasks_student_id", "student_id"),
        Index("idx_call_tasks_script_id", "script_id"),
        Index("idx_call_tasks_campaign_status", "campaign_id", "status"),
        Index(
            "idx_call_tasks_pending_scheduled",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<CallTask(id={self.id}, student_id={self.student_id}, status='{self.status}')>"


class CallLog(Base):
    """
    Detailed operational log containing full multi-turn conversation transcripts and latency stats.

    Attributes:
        id: Primary key identifier.
        task_id: Unique foreign key linking to the corresponding CallTask.
        transcript: JSONB array of conversational turns [{"role": "assistant", "text": "..."}].
        stt_provider: Name of the speech recognition provider used ('indic_conformer' | 'sarvam').
        llm_provider: Name of the language model provider used ('qwen3' | 'groq').
        tts_provider: Name of the speech synthesis provider used ('indicf5' | 'gtts').
        avg_latency_ms: Average turn turnaround latency in milliseconds.
        max_latency_ms: Peak turn turnaround latency in milliseconds.
        error_log: JSONB array recording exceptions or fallback events.
        created_at: Log creation timestamp.
    """

    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_tasks.id"), unique=True, nullable=False, index=True
    )
    transcript: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    stt_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tts_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    avg_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_log: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    task: Mapped["CallTask"] = relationship("CallTask", back_populates="log")

    __table_args__ = (
        Index("idx_call_logs_task", "task_id"),
    )

    def __repr__(self) -> str:
        return f"<CallLog(id={self.id}, task_id={self.task_id}, avg_ms={self.avg_latency_ms})>"
