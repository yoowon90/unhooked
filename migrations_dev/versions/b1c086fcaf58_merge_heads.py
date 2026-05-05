"""merge heads

Revision ID: b1c086fcaf58
Revises: 95707f49485c, add_image_url_to_wishitem
Create Date: 2026-05-03 11:10:40.098852

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c086fcaf58'
down_revision = ('95707f49485c', 'add_image_url_to_wishitem')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
