"""Added last purchased date

Revision ID: 1e06c6a8a47a
Revises: 9cc83064ecbb
Create Date: 2024-09-13 18:02:45.751853

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e06c6a8a47a'
down_revision = '9cc83064ecbb'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_purchase_date', sa.DateTime(timezone=True), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('last_purchase_date')

    # ### end Alembic commands ###