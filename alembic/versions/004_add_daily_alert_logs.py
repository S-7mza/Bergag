"""Add daily_alert_logs table for deduplicated 08:00 AM daily digest emails

Revision ID: 004_add_daily_alert_logs
Revises: 003_add_users_table
Create Date: 2026-11-28 18:35:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004_add_daily_alert_logs'
down_revision: Union[str, None] = '003_add_users_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if 'daily_alert_logs' not in tables:
        op.create_table(
            'daily_alert_logs',
            sa.Column('portal_id', sa.BigInteger(), sa.ForeignKey('tenders.portal_id', ondelete='CASCADE'), primary_key=True),
            sa.Column('ai_score', sa.Numeric(5, 2), server_default='0.0', nullable=False),
            sa.Column('cascade_score', sa.Numeric(5, 2), server_default='0.0', nullable=False),
            sa.Column('digest_date', sa.String(length=10), nullable=False),
            sa.Column('recipient_email', sa.String(length=255), nullable=True),
            sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        )
        op.create_index('idx_daily_alert_logs_digest_date', 'daily_alert_logs', ['digest_date'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if 'daily_alert_logs' in tables:
        op.drop_index('idx_daily_alert_logs_digest_date', table_name='daily_alert_logs')
        op.drop_table('daily_alert_logs')
