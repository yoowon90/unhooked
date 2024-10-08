"""Description of changes

Revision ID: a24c24eaae69
Revises: 0842e26653b0
Create Date: 2024-08-02 17:30:59.358984

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a24c24eaae69'
down_revision = '0842e26653b0'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.String(length=10000), nullable=True))
        batch_op.drop_column('notes')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wish_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sa.VARCHAR(length=10000), nullable=True))
        batch_op.drop_column('description')

    # ### end Alembic commands ###
