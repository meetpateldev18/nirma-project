"""Academic extensions, audit log, and database row-level security.

Revision ID: 004_academic_extensions_and_rls
Revises: 003_academic_hierarchy
Create Date: 2026-10-27 22:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_academic_extensions_and_rls'
down_revision: Union[str, None] = '003_academic_hierarchy'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add division_id to staff_users for Class Coordinator scoping
    op.add_column(
        'staff_users',
        sa.Column('division_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_staff_users_division_id',
        'staff_users',
        'academic_divisions',
        ['division_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_staff_users_division_id', 'staff_users', ['division_id'])

    # 2. Create academic_audit_logs table
    op.create_table(
        'academic_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=True),
        sa.Column('staff_email', sa.String(length=100), nullable=False),
        sa.Column('staff_role', sa.String(length=30), nullable=False),
        sa.Column('institute_code', sa.String(length=20), nullable=True),
        sa.Column('department_code', sa.String(length=20), nullable=True),
        sa.Column('target_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('target_filter', sa.JSON(), nullable=True),
        sa.Column('campaign_id', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['staff_id'], ['staff_users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_id'], ['call_campaigns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_logs_action_created', 'academic_audit_logs', ['action', 'created_at'])
    op.create_index('idx_audit_logs_staff', 'academic_audit_logs', ['staff_id'])

    # 3. Gate 2: PostgreSQL Row-Level Security (RLS) on students
    # Safe on PostgreSQL / Supabase, bypassed gracefully in SQLite test environments
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE students ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS rls_students_scoping ON students;")
        op.execute("""
            CREATE POLICY rls_students_scoping ON students
                FOR ALL
                USING (
                    current_setting('app.current_user_role', true) IS NULL
                    OR current_setting('app.current_user_role', true) = ''
                    OR current_setting('app.current_user_role', true) IN ('admin', 'super_admin')
                    OR (
                        current_setting('app.current_user_role', true) = 'dean'
                        AND (institute_id = NULLIF(current_setting('app.current_institute_id', true), '')::INT OR institute_id IS NULL)
                    )
                    OR (
                        current_setting('app.current_user_role', true) IN ('hod', 'operator')
                        AND (department_id = NULLIF(current_setting('app.current_department_id', true), '')::INT OR department_id IS NULL)
                    )
                    OR (
                        current_setting('app.current_user_role', true) = 'class_coordinator'
                        AND (division_id = NULLIF(current_setting('app.current_division_id', true), '')::INT OR division_id IS NULL)
                    )
                    OR (
                        current_setting('app.current_user_role', true) = 'faculty_mentor'
                        AND (mentor_id = NULLIF(current_setting('app.current_user_id', true), '')::INT OR mentor_id IS NULL)
                    )
                );
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS rls_students_scoping ON students;")
        op.execute("ALTER TABLE students DISABLE ROW LEVEL SECURITY;")

    op.drop_index('idx_audit_logs_staff', table_name='academic_audit_logs')
    op.drop_index('idx_audit_logs_action_created', table_name='academic_audit_logs')
    op.drop_table('academic_audit_logs')

    op.drop_index('idx_staff_users_division_id', table_name='staff_users')
    op.drop_constraint('fk_staff_users_division_id', 'staff_users', type_='foreignkey')
    op.drop_column('staff_users', 'division_id')
