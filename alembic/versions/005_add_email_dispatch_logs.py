"""Add email_dispatch_logs table for Admin Email History & Content Viewer

Revision ID: 005_add_email_dispatch_logs
Revises: 004_add_daily_alert_logs
Create Date: 2026-11-28 18:40:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '005_add_email_dispatch_logs'
down_revision: Union[str, None] = '004_add_daily_alert_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if 'email_dispatch_logs' not in tables:
        op.create_table(
            'email_dispatch_logs',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
            sa.Column('email_type', sa.String(length=32), server_default='daily_digest', nullable=False),
            sa.Column('recipient', sa.String(length=255), nullable=False),
            sa.Column('subject', sa.String(length=512), nullable=False),
            sa.Column('status', sa.String(length=32), server_default='sent', nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('offers_count', sa.Integer(), server_default='1', nullable=False),
            sa.Column('portal_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('html_content', sa.Text(), nullable=False),
            sa.Column('text_content', sa.Text(), nullable=True),
            sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        )
        op.create_index('idx_email_dispatch_logs_sent_at', 'email_dispatch_logs', ['sent_at'])
        op.create_index('idx_email_dispatch_logs_status', 'email_dispatch_logs', ['status'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if 'email_dispatch_logs' in tables:
        op.drop_index('idx_email_dispatch_logs_status', table_name='email_dispatch_logs')
        op.drop_index('idx_email_dispatch_logs_sent_at', table_name='email_dispatch_logs')
        op.drop_table('email_dispatch_logs')
