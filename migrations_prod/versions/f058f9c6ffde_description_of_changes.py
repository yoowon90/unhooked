"""Description of changes

Revision ID: f058f9c6ffde
Revises: 
Create Date: 2024-07-25 13:41:20.654135

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f058f9c6ffde'
down_revision = None
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()





def upgrade_():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('total_price', sa.Float(precision=100.0), nullable=True))

    # ### end Alembic commands ###


def downgrade_():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.drop_column('total_price')

    # ### end Alembic commands ###
