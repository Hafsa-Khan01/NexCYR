"""Database engine, session management and schema migration.

SQLite is used for development; the schema and engine setup stay
PostgreSQL-ready (only DATABASE_URL needs to change).
"""

import logging

from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from config import Config

logger = logging.getLogger("nexcyr.database")

connect_args = (
    {"check_same_thread": False}
    if Config.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(Config.DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Legacy column -> new column data preservation maps.
# Used once when an existing table is rebuilt to the current schema.
LEGACY_COLUMN_MAPS = {
    "soc_events": {"message": "title"},
    "purple_team_tests": {
        "name": "test_name",
        "technique": "test_type",
        "objective": "description",
        "status": "execution_status",
        "detection_status": "detection_result",
    },
    "wifi_assessments": {
        "ssid": "target",
        "status": "assessment_status",
    },
}


def _rebuild_table(table, existing_columns):
    """Rebuild one table to the current model, copying preserved data."""
    mapping = LEGACY_COLUMN_MAPS.get(table.name, {})
    old_name = f"{table.name}_legacy_backup"

    copy_pairs = []
    for column in table.columns:
        source = mapping.get(column.name, column.name)
        if source in existing_columns:
            copy_pairs.append((column.name, source))

    with engine.begin() as conn:
        conn.exec_driver_sql(
            f'ALTER TABLE "{table.name}" RENAME TO "{old_name}"'
        )
        table.create(bind=conn)
        if copy_pairs:
            new_cols = ", ".join(f'"{n}"' for n, _ in copy_pairs)
            old_cols = ", ".join(f'"{o}"' for _, o in copy_pairs)
            conn.exec_driver_sql(
                f'INSERT INTO "{table.name}" ({new_cols}) '
                f'SELECT {old_cols} FROM "{old_name}"'
            )
        conn.exec_driver_sql(f'DROP TABLE "{old_name}"')

    logger.info(
        "Migrated table %s (%d columns preserved)",
        table.name,
        len(copy_pairs),
    )


def _add_missing_columns(table, missing_columns):
    """Additively add new columns without rebuilding the table.

    Used when the desired schema is a strict superset of the existing one
    (pure additions). Preserves rows, indexes and foreign keys in place.
    """
    with engine.begin() as conn:
        for column in table.columns:
            if column.name not in missing_columns:
                continue
            col_type = column.type.compile(engine.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            if not column.nullable:
                ddl += " NOT NULL"
            if column.server_default is not None:
                arg = column.server_default.arg
                if hasattr(arg, "text"):
                    arg = arg.text
                ddl += f" DEFAULT '{arg}'"
            conn.exec_driver_sql(ddl)

    logger.info(
        "Added %d column(s) to %s: %s",
        len(missing_columns),
        table.name,
        ", ".join(sorted(missing_columns)),
    )


def init_db():
    """Create missing tables and migrate legacy tables without data loss."""
    import models  # noqa: F401  (register all mappers)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table.name)
        }
        desired_columns = {column.name for column in table.columns}
        if existing_columns == desired_columns:
            continue

        missing = desired_columns - existing_columns
        extra = existing_columns - desired_columns
        needs_rename = table.name in LEGACY_COLUMN_MAPS

        # Pure additive change with no legacy renames -> safe in-place ALTER.
        if missing and not extra and not needs_rename:
            try:
                _add_missing_columns(table, missing)
                continue
            except Exception:
                logger.exception(
                    "Additive migration of %s failed; falling back to rebuild",
                    table.name,
                )

        try:
            _rebuild_table(table, existing_columns)
        except Exception:
            logger.exception(
                "Migration of table %s failed; recreating schema", table.name
            )
            with engine.begin() as conn:
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table.name}"')
                conn.exec_driver_sql(
                    f'DROP TABLE IF EXISTS "{table.name}_legacy_backup"'
                )

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ready at %s", Config.DATABASE_URL)
