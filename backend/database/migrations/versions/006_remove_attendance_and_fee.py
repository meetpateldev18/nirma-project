"""Remove attendance_pct and pending_fee_inr from students

Revision ID: 006_remove_attendance_and_fee
Revises: 005_prog_coord_rls
Create Date: 2026-11-13 11:22:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_remove_attendance_and_fee'
down_revision = '005_prog_coord_rls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Attendance and Fee are handled outside the calling assistant system
    op.drop_column('students', 'attendance_pct')
    op.drop_column('students', 'pending_fee_inr')


def downgrade() -> None:
    op.add_column('students', sa.Column('pending_fee_inr', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
    op.add_column('students', sa.Column('attendance_pct', sa.Numeric(5, 2), nullable=False, server_default='100.00'))
