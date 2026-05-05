"""drop unused google_client_id and google_client_secret columns from user

These columns were added by the initial Gmail connector design that stored
OAuth credentials per-user. The current design uses application-level
credentials in .env, so the per-user columns are dead.

Revision ID: 2a4f1c8e9b0d
Revises: 1b09da4c74d0
Create Date: 2026-05-03 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a4f1c8e9b0d'
down_revision = '1b09da4c74d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('google_client_secret')
        batch_op.drop_column('google_client_id')


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_client_id', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('google_client_secret', sa.String(length=300), nullable=True))
