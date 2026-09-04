from datetime import datetime

from sqlalchemy.orm import DeclarativeBase

from app.db.types import UTCDateTime

# Consistent naming convention so constraint names are stable across SQLite and
# a future PostgreSQL target (matters for Alembic autogenerate if/when it's added).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    # Every `Mapped[datetime]` column in every model uses UTCDateTime without
    # having to name it at each call site -- see app.db.types for why this
    # matters (a naive read-back from SQLite is the root cause of timestamps
    # displaying hours off from the client's local time).
    type_annotation_map = {datetime: UTCDateTime}


Base.metadata.naming_convention = NAMING_CONVENTION
