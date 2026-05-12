"""initial

Revision ID: 0001
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_username', sa.String(64), nullable=True),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('role', sa.Enum('owner','manager','employee', name='userrole'), nullable=False, server_default='employee'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('language_code', sa.String(5), nullable=False, server_default='ru'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_users'),
        sa.UniqueConstraint('telegram_id', name='uq_users_telegram_id'),
        sa.UniqueConstraint('phone', name='uq_users_phone'),
    )
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'])
    op.create_index('ix_users_role_active', 'users', ['role', 'is_active'])

    op.create_table('site_objects',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('address', sa.String(500), nullable=False),
        sa.Column('client_name', sa.String(200), nullable=True),
        sa.Column('client_phone', sa.String(20), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('radius_meters', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('status', sa.Enum('active','completed','paused', name='objectstatus'), nullable=False, server_default='active'),
        sa.Column('planned_hours', sa.Numeric(8,2), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('manager_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('qr_code', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_site_objects'),
        sa.UniqueConstraint('qr_code', name='uq_site_objects_qr_code'),
    )
    op.create_index('ix_site_objects_status', 'site_objects', ['status'])
    op.create_index('ix_site_objects_manager_id', 'site_objects', ['manager_id'])

    op.create_table('employee_objects',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('employee_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_object_id', sa.BigInteger(), sa.ForeignKey('site_objects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_employee_objects'),
        sa.UniqueConstraint('employee_id', 'site_object_id', name='uq_employee_object'),
    )

    op.create_table('shifts',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('employee_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_object_id', sa.BigInteger(), sa.ForeignKey('site_objects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Enum('active','completed','cancelled', name='shiftstatus'), nullable=False, server_default='active'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('start_latitude', sa.Float(), nullable=True),
        sa.Column('start_longitude', sa.Float(), nullable=True),
        sa.Column('end_latitude', sa.Float(), nullable=True),
        sa.Column('end_longitude', sa.Float(), nullable=True),
        sa.Column('total_hours', sa.Numeric(6,2), nullable=True),
        sa.Column('overtime_hours', sa.Numeric(6,2), nullable=True, server_default='0'),
        sa.Column('is_late', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('late_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_shifts'),
    )
    op.create_index('ix_shifts_employee_id', 'shifts', ['employee_id'])
    op.create_index('ix_shifts_object_id', 'shifts', ['site_object_id'])
    op.create_index('ix_shifts_status', 'shifts', ['status'])
    op.create_index('ix_shifts_started_at', 'shifts', ['started_at'])

    op.create_table('location_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('employee_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('shift_id', sa.BigInteger(), sa.ForeignKey('shifts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('accuracy', sa.Float(), nullable=True),
        sa.Column('is_on_site', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_location_logs'),
    )

    op.create_table('tasks',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('creator_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assignee_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('site_object_id', sa.BigInteger(), sa.ForeignKey('site_objects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.Enum('pending','in_progress','done','overdue', name='taskstatus'), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Enum('low','medium','high', name='taskpriority'), nullable=False, server_default='medium'),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completion_report', sa.Text(), nullable=True),
        sa.Column('attachments', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_tasks'),
    )

    op.create_table('photos',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('file_id', sa.String(200), nullable=False),
        sa.Column('s3_key', sa.String(500), nullable=True),
        sa.Column('s3_url', sa.String(1000), nullable=True),
        sa.Column('photo_type', sa.Enum('before','during','after','task_report', name='phototype'), nullable=False),
        sa.Column('shift_id', sa.BigInteger(), sa.ForeignKey('shifts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('task_id', sa.BigInteger(), sa.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('site_object_id', sa.BigInteger(), sa.ForeignKey('site_objects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('uploaded_by_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('ai_analysis', postgresql.JSON(), nullable=True),
        sa.Column('has_helmet', sa.Boolean(), nullable=True),
        sa.Column('has_vest', sa.Boolean(), nullable=True),
        sa.Column('has_gloves', sa.Boolean(), nullable=True),
        sa.Column('progress_pct', sa.Integer(), nullable=True),
        sa.Column('ai_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_photos'),
    )

    op.create_table('notifications',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('recipient_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('notification_type', sa.Enum('arrived','left','late','overtime','no_show','left_site','task_overdue', name='notificationtype'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra_data', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_notifications'),
    )

    op.create_table('work_schedules',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('employee_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_object_id', sa.BigInteger(), sa.ForeignKey('site_objects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('planned_start', sa.String(5), nullable=True),
        sa.Column('planned_end', sa.String(5), nullable=True),
        sa.Column('is_day_off', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_work_schedules'),
        sa.UniqueConstraint('employee_id', 'work_date', name='uq_employee_date'),
    )

    op.create_table('audit_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity', sa.String(100), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=True),
        sa.Column('old_value', postgresql.JSON(), nullable=True),
        sa.Column('new_value', postgresql.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_audit_logs'),
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('work_schedules')
    op.drop_table('notifications')
    op.drop_table('photos')
    op.drop_table('tasks')
    op.drop_table('location_logs')
    op.drop_table('shifts')
    op.drop_table('employee_objects')
    op.drop_table('site_objects')
    op.drop_table('users')
