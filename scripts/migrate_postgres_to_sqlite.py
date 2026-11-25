"""Copy existing PostgreSQL rows into the matching SQLite schema.

Run from backend/:
  python scripts/migrate_postgres_to_sqlite.py          # dry run
  python scripts/migrate_postgres_to_sqlite.py --apply   # import rows

Set LEGACY_DATABASE_URL in backend/.env. The script refuses to merge into
non-empty target tables and preserves source primary keys and relationships.
"""
import argparse
import os
import sys
from sqlalchemy import create_engine, inspect, select, insert, func, MetaData, Table
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine as target_engine
from app import models  # noqa: F401


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually import rows; without this flag only inspect counts")
    args = parser.parse_args()
    source_url = settings.legacy_database_url or os.getenv("LEGACY_DATABASE_URL")
    if not source_url:
        raise SystemExit("LEGACY_DATABASE_URL is not set. Add it to backend/.env; do not paste it into chat.")
    parsed = make_url(source_url)
    if parsed.get_backend_name() != "postgresql":
        raise SystemExit("LEGACY_DATABASE_URL must point to the old PostgreSQL database.")
    # Use psycopg v3, which is installed by backend/requirements.txt.
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    source_engine = create_engine(parsed, pool_pre_ping=True)
    try:
        source_inspector = inspect(source_engine)
        source_tables = set(source_inspector.get_table_names())
        target_tables = set(inspect(target_engine).get_table_names())
        expected = [table for table in Base.metadata.sorted_tables if table.name in source_tables]
        missing = sorted(source_tables.intersection(Base.metadata.tables) - target_tables)
        if missing:
            raise SystemExit(f"Target schema is missing tables: {', '.join(missing)}. Run alembic upgrade head first.")
        source_metadata = MetaData()
        reflected = {table.name: Table(table.name, source_metadata, autoload_with=source_engine) for table in expected}
        for target_table in expected:
            source_columns = set(reflected[target_table.name].columns.keys())
            target_columns = set(target_table.columns.keys())
            unexpected = sorted(source_columns - target_columns)
            if unexpected:
                raise SystemExit(f"Source table {target_table.name} has columns not mapped by the new schema: {', '.join(unexpected)}")
        counts = {}
        with source_engine.connect() as source, target_engine.connect() as target:
            for table in expected:
                source_table = reflected[table.name]
                counts[table.name] = source.execute(select(func.count()).select_from(source_table)).scalar_one()
                target_count = target.execute(select(func.count()).select_from(table)).scalar_one() if table.name in target_tables else 0
                if args.apply and target_count:
                    raise SystemExit(f"Target table {table.name} already has {target_count} rows. Use a fresh empty SQLite database to avoid merging data.")
        print("Legacy database table counts:")
        for name, count in counts.items(): print(f"  {name}: {count}")
        if not args.apply:
            print("\nDry run only. No rows were changed. Re-run with --apply to import.")
            return
        Base.metadata.create_all(target_engine)
        imported = {}
        with source_engine.connect() as source, target_engine.begin() as target:
            for table in expected:
                source_table = reflected[table.name]
                result = source.execute(select(source_table))
                rows = [dict(row._mapping) for row in result]
                if rows:
                    target.execute(insert(table), rows)
                imported[table.name] = len(rows)
        print("\nImport completed:")
        for name, count in imported.items(): print(f"  {name}: {count}")
        print("Verify these counts against the source before switching the application.")
    finally:
        source_engine.dispose()

if __name__ == "__main__":
    main()
