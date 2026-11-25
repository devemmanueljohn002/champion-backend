"""Add live examination timing and subject fields."""
from alembic import op
import sqlalchemy as sa

revision = "0002_examination_live_fields"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("Examination")}
    with op.batch_alter_table("Examination") as batch_op:
        if "subjectId" not in columns:
            batch_op.add_column(sa.Column("subjectId", sa.String(), nullable=True))
            batch_op.create_foreign_key(
                "fk_examination_subject",
                "Subject",
                ["subjectId"],
                ["id"],
            )
        if "actualStartedAt" not in columns:
            batch_op.add_column(sa.Column("actualStartedAt", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("Examination") as batch_op:
        batch_op.drop_column("actualStartedAt")
        batch_op.drop_constraint("fk_examination_subject", type_="foreignkey")
        batch_op.drop_column("subjectId")
