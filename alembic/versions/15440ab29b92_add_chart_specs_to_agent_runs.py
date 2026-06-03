"""add_chart_specs_to_agent_runs

Revision ID: 15440ab29b92
Revises: 33deaf934141
Create Date: 2026-06-04 00:19:51.173715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15440ab29b92'
down_revision: Union[str, Sequence[str], None] = '33deaf934141'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add chart_specs column to agent_runs."""
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chart_specs', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove chart_specs column from agent_runs."""
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.drop_column('chart_specs')
