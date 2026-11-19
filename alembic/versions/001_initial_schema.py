"""Initial database schema with pgvector, pg_trgm, and layered procurement tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-19 15:30:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable PostgreSQL Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

    # 2. Raw Ingestion Log
    op.create_table(
        'raw_ingestion_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('portal_id', sa.BigInteger(), nullable=True),
        sa.Column('page_type', sa.String(length=32), nullable=False), # 'listing', 'detail', 'result'
        sa.Column('http_status', sa.Integer(), nullable=False),
        sa.Column('html_content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False), # SHA-256
        sa.Column('scraper_version', sa.String(length=16), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_raw_portal_id', 'raw_ingestion_log', ['portal_id'])
    op.create_index('idx_raw_content_hash', 'raw_ingestion_log', ['content_hash'])

    # 3. Buyers
    op.create_table(
        'buyers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('slug', sa.String(length=255), unique=True, nullable=False),
        sa.Column('official_name', sa.Text(), nullable=False),
        sa.Column('buyer_type', sa.String(length=64), nullable=False),
        sa.Column('region', sa.String(length=64), nullable=True),
        sa.Column('city', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.execute('CREATE INDEX idx_buyers_name_trgm ON buyers USING gin (official_name gin_trgm_ops);')

    # 4. Tenders
    op.create_table(
        'tenders',
        sa.Column('portal_id', sa.BigInteger(), primary_key=True),
        sa.Column('source_type', sa.String(length=32), server_default='bdc', nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=False),
        sa.Column('compound_natural_key', sa.String(length=255), nullable=False),
        sa.Column('buyer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('buyers.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('main_category', sa.String(length=32), nullable=False),
        sa.Column('prestation_type', sa.Text(), nullable=True),
        sa.Column('execution_location', sa.Text(), nullable=True),
        sa.Column('normalized_city', sa.String(length=64), nullable=True),
        sa.Column('normalized_region', sa.String(length=64), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('attachment_available', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('attachment_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_tenders_deadline', 'tenders', ['deadline_at'])
    op.create_index('idx_tenders_natural_key', 'tenders', ['compound_natural_key'])
    op.execute("CREATE INDEX idx_tenders_status_deadline ON tenders(status, deadline_at) WHERE status = 'active';")
    op.execute('CREATE INDEX idx_tenders_title_trgm ON tenders USING gin (title gin_trgm_ops);')

    # 5. Line Items
    op.create_table(
        'line_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tender_id', sa.BigInteger(), sa.ForeignKey('tenders.portal_id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_order', sa.Integer(), nullable=False),
        sa.Column('designation', sa.Text(), nullable=False),
        sa.Column('technical_specs', sa.Text(), nullable=True),
        sa.Column('unit', sa.String(length=32), server_default='U', nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('tva_rate', sa.Numeric(precision=5, scale=2), server_default='20.00', nullable=True),
        sa.Column('warranty_required', sa.Text(), nullable=True),
        sa.Column('extracted_brand', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_line_items_tender', 'line_items', ['tender_id'])
    op.execute('CREATE INDEX idx_line_items_designation_trgm ON line_items USING gin (designation gin_trgm_ops);')

    # 6. Awards / Results
    op.create_table(
        'awards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tender_id', sa.BigInteger(), sa.ForeignKey('tenders.portal_id', ondelete='SET NULL'), nullable=True),
        sa.Column('compound_ref_key', sa.String(length=255), nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=False),
        sa.Column('buyer_name_raw', sa.Text(), nullable=False),
        sa.Column('title_raw', sa.Text(), nullable=False),
        sa.Column('winner_name', sa.Text(), nullable=False),
        sa.Column('winner_identifier', sa.String(length=64), nullable=True),
        sa.Column('amount_ttc', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('devis_received_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False), # 'Attribué', 'Infructueux'
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scraped_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_awards_tender_id', 'awards', ['tender_id'])
    op.create_index('idx_awards_compound_key', 'awards', ['compound_ref_key'])
    op.execute('CREATE INDEX idx_awards_winner_trgm ON awards USING gin (winner_name gin_trgm_ops);')

    # 7. Tender Embeddings (pgvector)
    op.create_table(
        'tender_embeddings',
        sa.Column('tender_id', sa.BigInteger(), sa.ForeignKey('tenders.portal_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('embedded_content_hash', sa.String(length=64), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.execute('CREATE INDEX idx_tender_embeddings_vector ON tender_embeddings USING hnsw (embedding vector_cosine_ops);')

    # 8. Company Profiles
    op.create_table(
        'company_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('profile_name', sa.String(length=128), nullable=False),
        sa.Column('config_yaml', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )

    # 9. Profile Matches
    op.create_table(
        'profile_matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('company_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tender_id', sa.BigInteger(), sa.ForeignKey('tenders.portal_id', ondelete='CASCADE'), nullable=False),
        sa.Column('overall_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('coverage_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('semantic_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('feasibility_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('commercial_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('decision_recommendation', sa.String(length=16), nullable=False),
        sa.Column('line_item_matches', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('red_flags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('llm_reasoning', sa.Text(), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('profile_id', 'tender_id', name='uq_profile_tender_match')
    )
    op.create_index('idx_profile_matches_score', 'profile_matches', ['profile_id', 'overall_score'])

    # 10. User Actions (Feedback Loop)
    op.create_table(
        'user_tender_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('company_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tender_id', sa.BigInteger(), sa.ForeignKey('tenders.portal_id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False), # 'viewed', 'shortlisted', 'bidded', 'won', 'lost', 'rejected'
        sa.Column('rejection_reason', sa.String(length=64), nullable=True),
        sa.Column('user_notes', sa.Text(), nullable=True),
        sa.Column('actioned_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('profile_id', 'tender_id', 'action', name='uq_user_action')
    )


def downgrade() -> None:
    op.drop_table('user_tender_actions')
    op.drop_table('profile_matches')
    op.drop_table('company_profiles')
    op.drop_table('tender_embeddings')
    op.drop_table('awards')
    op.drop_table('line_items')
    op.drop_table('tenders')
    op.drop_table('buyers')
    op.drop_table('raw_ingestion_log')

