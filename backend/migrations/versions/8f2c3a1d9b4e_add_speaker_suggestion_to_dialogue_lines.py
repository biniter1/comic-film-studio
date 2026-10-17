"""add speaker_suggestion to dialogue_lines

Revision ID: 8f2c3a1d9b4e
Revises: aa090d0cca50
Create Date: 2026-10-17 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f2c3a1d9b4e"
down_revision: Union[str, Sequence[str], None] = "aa090d0cca50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("dialogue_lines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("speaker_suggestion", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("dialogue_lines", schema=None) as batch_op:
        batch_op.drop_column("speaker_suggestion")
