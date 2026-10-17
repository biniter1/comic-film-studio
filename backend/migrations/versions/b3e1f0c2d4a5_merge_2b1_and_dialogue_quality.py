"""merge heads: phase2b1 character refs + dialogue speaker_suggestion

Revision ID: b3e1f0c2d4a5
Revises: 120fc71d23c5, 8f2c3a1d9b4e
"""

from collections.abc import Sequence
from typing import Union

revision: str = "b3e1f0c2d4a5"
down_revision: Union[str, Sequence[str], None] = ("120fc71d23c5", "8f2c3a1d9b4e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
