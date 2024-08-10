"""Description of changes

Revision ID: c345578a0e96
Revises: a24c24eaae69
Create Date: 2024-08-10 16:07:00.332840

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c345578a0e96'
down_revision = 'a24c24eaae69'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('wish_to_unhook_period', sa.Interval(), nullable=True))
        batch_op.add_column(sa.Column('wish_to_purchase_period', sa.Interval(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.drop_column('wish_to_purchase_period')
        batch_op.drop_column('wish_to_unhook_period')

    # ### end Alembic commands ###