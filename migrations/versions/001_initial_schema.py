"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-07-29

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_username', sa.String(length=255), nullable=True),
        sa.Column('moodle_username', sa.String(length=255), nullable=True),
        sa.Column('moodle_password_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('groq_api_key_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('moodle_url', sa.String(length=255), nullable=False, server_default='https://moodle.iugaza.edu.ps'),
        sa.Column('language', sa.String(length=10), nullable=False, server_default='ar'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('last_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_telegram_chat_id'), 'users', ['telegram_chat_id'], unique=True)

    op.create_table(
        'user_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notify_files', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('notify_assignments', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('notify_quizzes', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('notify_folders', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('digest_mode', sa.String(length=20), nullable=False, server_default='instant'),
        sa.Column('digest_time', sa.String(length=10), nullable=False, server_default='20:00'),
        sa.Column('quiet_hours_start', sa.String(length=10), nullable=True),
        sa.Column('quiet_hours_end', sa.String(length=10), nullable=True),
        sa.Column('muted_courses', sa.JSON(), nullable=False),
        sa.Column('ai_summaries_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_user_settings_id'), 'user_settings', ['id'], unique=False)
    op.create_index(op.f('ix_user_settings_user_id'), 'user_settings', ['user_id'], unique=True)

    op.create_table(
        'course_content',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content_json', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_course_content_id'), 'course_content', ['id'], unique=False)
    op.create_index(op.f('ix_course_content_user_id'), 'course_content', ['user_id'], unique=False)

    op.create_table(
        'calendar_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('events_json', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_calendar_events_id'), 'calendar_events', ['id'], unique=False)
    op.create_index(op.f('ix_calendar_events_user_id'), 'calendar_events', ['user_id'], unique=False)

    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('content_summary', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_logs_id'), 'notification_logs', ['id'], unique=False)
    op.create_index(op.f('ix_notification_logs_user_id'), 'notification_logs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('notification_logs')
    op.drop_table('calendar_events')
    op.drop_table('course_content')
    op.drop_table('user_settings')
    op.drop_table('users')
