"""Academic hierarchy and student data scoping schema.

Revision ID: 003_academic_hierarchy
Revises: 002_optimized_indexes
Create Date: 2026-10-27 21:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_academic_hierarchy'
down_revision: Union[str, None] = '002_optimized_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create institutions table
    op.create_table(
        'institutions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('domain', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('domain'),
    )

    # 2. Create institutes table
    op.create_table(
        'institutes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('institution_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('director_name', sa.String(length=100), nullable=True),
        sa.Column('contact_email', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('idx_institutes_institution_id', 'institutes', ['institution_id'])

    # 3. Create departments table
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('institute_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('hod_name', sa.String(length=100), nullable=True),
        sa.Column('hod_email', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['institute_id'], ['institutes.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('institute_id', 'code', name='uq_departments_inst_code'),
    )
    op.create_index('idx_departments_institute_id', 'departments', ['institute_id'])

    # 4. Create academic_programs table
    op.create_table(
        'academic_programs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False, server_default='UG'),
        sa.Column('duration_semesters', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department_id', 'code', name='uq_programs_dept_code'),
    )
    op.create_index('idx_academic_programs_department_id', 'academic_programs', ['department_id'])

    # 5. Create academic_batches table
    op.create_table(
        'academic_batches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('admission_year', sa.Integer(), nullable=False),
        sa.Column('graduating_year', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['program_id'], ['academic_programs.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'admission_year', name='uq_batches_program_year'),
    )
    op.create_index('idx_academic_batches_program_id', 'academic_batches', ['program_id'])

    # 6. Create academic_divisions table
    op.create_table(
        'academic_divisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('current_semester', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['batch_id'], ['academic_batches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id', 'code', name='uq_divisions_batch_code'),
    )
    op.create_index('idx_academic_divisions_batch_id', 'academic_divisions', ['batch_id'])

    # 7. Add hierarchy scoping columns to staff_users
    op.add_column('staff_users', sa.Column('institute_id', sa.Integer(), nullable=True))
    op.add_column('staff_users', sa.Column('department_id', sa.Integer(), nullable=True))
    op.add_column('staff_users', sa.Column('institute_code', sa.String(length=20), nullable=True))
    op.add_column('staff_users', sa.Column('department_code', sa.String(length=20), nullable=True))
    op.create_foreign_key('fk_staff_users_institute', 'staff_users', 'institutes', ['institute_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_staff_users_department', 'staff_users', 'departments', ['department_id'], ['id'], ondelete='SET NULL')

    # 8. Add hierarchy columns and performance fields to students
    op.add_column('students', sa.Column('institute_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('department_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('program_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('batch_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('division_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('mentor_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('lab_batch', sa.String(length=10), nullable=True))
    op.add_column('students', sa.Column('pending_fee_inr', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
    op.add_column('students', sa.Column('attendance_pct', sa.Numeric(5, 2), nullable=False, server_default='100.00'))

    op.create_foreign_key('fk_students_institute', 'students', 'institutes', ['institute_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_students_department', 'students', 'departments', ['department_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_students_program', 'students', 'academic_programs', ['program_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_students_batch', 'students', 'academic_batches', ['batch_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_students_division', 'students', 'academic_divisions', ['division_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_students_mentor', 'students', 'staff_users', ['mentor_id'], ['id'], ondelete='SET NULL')

    op.create_index('idx_students_department_id', 'students', ['department_id'])
    op.create_index('idx_students_institute_id', 'students', ['institute_id'])


def downgrade() -> None:
    op.drop_index('idx_students_institute_id', table_name='students')
    op.drop_index('idx_students_department_id', table_name='students')
    op.drop_constraint('fk_students_mentor', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_division', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_batch', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_program', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_department', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_institute', 'students', type_='foreignkey')

    op.drop_column('students', 'attendance_pct')
    op.drop_column('students', 'pending_fee_inr')
    op.drop_column('students', 'lab_batch')
    op.drop_column('students', 'mentor_id')
    op.drop_column('students', 'division_id')
    op.drop_column('students', 'batch_id')
    op.drop_column('students', 'program_id')
    op.drop_column('students', 'department_id')
    op.drop_column('students', 'institute_id')

    op.drop_constraint('fk_staff_users_department', 'staff_users', type_='foreignkey')
    op.drop_constraint('fk_staff_users_institute', 'staff_users', type_='foreignkey')
    op.drop_column('staff_users', 'department_code')
    op.drop_column('staff_users', 'institute_code')
    op.drop_column('staff_users', 'department_id')
    op.drop_column('staff_users', 'institute_id')

    op.drop_table('academic_divisions')
    op.drop_table('academic_batches')
    op.drop_table('academic_programs')
    op.drop_table('departments')
    op.drop_table('institutes')
    op.drop_table('institutions')
