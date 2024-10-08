"""Description of changes

Revision ID: 9b8450bb3163
Revises: fc0b9df237ad
Create Date: 2024-08-19 18:51:19.358081

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b8450bb3163'
down_revision = 'fc0b9df237ad'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()





def upgrade_():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('favorited', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade_():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.drop_column('favorited')

    # ### end Alembic commands ###

