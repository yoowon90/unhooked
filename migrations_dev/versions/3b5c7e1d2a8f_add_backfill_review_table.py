"""add backfill_review table

Persists every Gmail email the user reviewed in the backfill flow (approved
or denied) so denials don't cause the same emails to reappear on the next
scan.

Revision ID: 3b5c7e1d2a8f
Revises: 2a4f1c8e9b0d
Create Date: 2026-05-04 11:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3b5c7e1d2a8f'
down_revision = '2a4f1c8e9b0d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'backfill_review',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source_email_id', sa.String(length=200), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source_email_id', name='uq_backfill_review_user_email'),
    )


def downgrade():
    op.drop_table('backfill_review')
