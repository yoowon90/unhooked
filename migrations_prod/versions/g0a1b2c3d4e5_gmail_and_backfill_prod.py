"""add gmail connector + backfill fields + backfill_review table (prod)

Brings prod up to parity with the dev migration chain:
  - User: add gmail_access_token, gmail_refresh_token, gmail_token_expiry,
    gmail_connected_email (per-user OAuth state)
  - WishItem: add backfilled (bool), source_email_id (str) for tracking which
    items came from the Gmail backfill flow
  - New table: backfill_review (audit row per email reviewed via backfill)

Note: backfill_review may already exist if SQLAlchemy.create_all() ran in
this DB before the migration was applied. The CREATE TABLE IF NOT EXISTS
makes this safe.

Revision ID: g0a1b2c3d4e5
Revises: add_image_url_to_wishitem_prod
Create Date: 2026-05-04 20:50:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'g0a1b2c3d4e5'
down_revision = 'add_image_url_to_wishitem_prod'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gmail_access_token', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('gmail_refresh_token', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('gmail_token_expiry', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('gmail_connected_email', sa.String(length=150), nullable=True))

    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('backfilled', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('source_email_id', sa.String(length=200), nullable=True))

    op.execute("""
        CREATE TABLE IF NOT EXISTS backfill_review (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            source_email_id VARCHAR(200) NOT NULL,
            decision VARCHAR(20) NOT NULL,
            reviewed_at DATETIME,
            FOREIGN KEY(user_id) REFERENCES "user"(id),
            CONSTRAINT uq_backfill_review_user_email UNIQUE (user_id, source_email_id)
        )
    """)


def downgrade_():
    op.drop_table('backfill_review')

    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.drop_column('source_email_id')
        batch_op.drop_column('backfilled')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('gmail_connected_email')
        batch_op.drop_column('gmail_token_expiry')
        batch_op.drop_column('gmail_refresh_token')
        batch_op.drop_column('gmail_access_token')
