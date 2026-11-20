"""Add users table for real database-backed authentication and RBAC

Revision ID: 003_add_users_table
Revises: 002_add_ingestion_batches
Create Date: 2026-11-20 01:15:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_add_users_table'
down_revision: Union[str, None] = '002_add_ingestion_batches'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure uuid extension is available
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if 'users' not in tables:
        op.create_table(
            'users',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
            sa.Column('email', sa.String(length=255), unique=True, nullable=False),
            sa.Column('username', sa.String(length=64), unique=True, nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('full_name', sa.String(length=255), nullable=False),
            sa.Column('role', sa.String(length=32), server_default='viewer', nullable=False),
            sa.Column('title', sa.String(length=128), server_default='Collaborateur', nullable=False),
            sa.Column('avatar_color', sa.String(length=32), server_default='emerald', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
        )
        op.create_index('idx_users_email', 'users', ['email'])
        op.create_index('idx_users_username', 'users', ['username'])
        op.create_index('idx_users_role', 'users', ['role'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if 'users' in tables:
        op.drop_index('idx_users_role', table_name='users')
        op.drop_index('idx_users_username', table_name='users')
        op.drop_index('idx_users_email', table_name='users')
        op.drop_table('users')
