"""add alert event bar deduplication

Revision ID: 27acb77f4b1d
Revises: c9cc05d13b33
Create Date: 2026-10-20 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "27acb77f4b1d"
down_revision: Union[str, Sequence[str], None] = "c9cc05d13b33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("alert_events") as batch_op:
        batch_op.add_column(
            sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_alert_event_data_timestamp", ["alert_id", "data_timestamp"]
        )


def downgrade() -> None:
    with op.batch_alter_table("alert_events") as batch_op:
        batch_op.drop_constraint("uq_alert_event_data_timestamp", type_="unique")
        batch_op.drop_column("data_timestamp")
