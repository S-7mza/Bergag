"""Add ingestion_batches table for persistent batch ledger

Revision ID: 002_add_ingestion_batches
Revises: 001_initial_schema
Create Date: 2026-11-19 23:45:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_add_ingestion_batches'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ingestion_batches',
        sa.Column('batch_id', sa.String(length=64), primary_key=True),
        sa.Column('trigger_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('pages_requested', sa.Integer(), server_default='2', nullable=False),
        sa.Column('pages_completed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cards_scraped', sa.Integer(), server_default='0', nullable=False),
        sa.Column('tenders_ingested', sa.Integer(), server_default='0', nullable=False),
        sa.Column('line_items_extracted', sa.Integer(), server_default='0', nullable=False),
        sa.Column('alerts_dispatched', sa.Integer(), server_default='0', nullable=False),
        sa.Column('quality_score', sa.Float(), server_default='95.0', nullable=False),
        sa.Column('errors_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=128), server_default='Système (Daemon)', nullable=False),
        sa.Column('first_bdc_id', sa.BigInteger(), nullable=True),
        sa.Column('last_bdc_id', sa.BigInteger(), nullable=True),
        sa.Column('current_step', sa.Text(), nullable=True),
        sa.Column('current_phase', sa.String(length=32), server_default='completed', nullable=False),
        sa.Column('progress_pct', sa.Integer(), server_default='100', nullable=False)
    )
    op.create_index('idx_batches_started_at', 'ingestion_batches', ['started_at'])
    op.create_index('idx_batches_status', 'ingestion_batches', ['status'])


def downgrade() -> None:
    op.drop_index('idx_batches_status', table_name='ingestion_batches')
    op.drop_index('idx_batches_started_at', table_name='ingestion_batches')
    op.drop_table('ingestion_batches')
