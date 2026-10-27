"""Add program_id to staff_users and extend RLS for Program Coordinator.

Revision ID: 005_prog_coord_rls
Revises: 004_academic_extensions_and_rls
Create Date: 2026-10-27 23:16:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_prog_coord_rls'
down_revision: Union[str, None] = '004_academic_extensions_and_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add program_id to staff_users for Program Coordinator scoping
    op.add_column(
        'staff_users',
        sa.Column('program_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_staff_users_program_id',
        'staff_users',
        'academic_programs',
        ['program_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('idx_staff_users_program_id', 'staff_users', ['program_id'])

    # 2. Update PostgreSQL Row-Level Security policy on students
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
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
                        current_setting('app.current_user_role', true) = 'program_coordinator'
                        AND (program_id = NULLIF(current_setting('app.current_program_id', true), '')::INT OR program_id IS NULL)
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

    op.drop_index('idx_staff_users_program_id', table_name='staff_users')
    op.drop_constraint('fk_staff_users_program_id', 'staff_users', type_='foreignkey')
    op.drop_column('staff_users', 'program_id')
