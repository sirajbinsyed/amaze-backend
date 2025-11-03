import os
import glob
import psycopg
from psycopg.rows import tuple_row

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/erp")

def ensure_migrations_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
        create table if not exists schema_migrations (
            id bigserial primary key,
            filename text unique not null,
            applied_at timestamptz not null default now()
        );
        """)

def applied_files(conn):
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("select filename from schema_migrations order by id")
        return {r[0] for r in cur.fetchall()}

def apply_sql(conn, path):
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute("insert into schema_migrations (filename) values (%s)", (os.path.basename(path),))

def main():
    print("[v0] Connecting to DB:", DATABASE_URL)
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        ensure_migrations_table(conn)
        already = applied_files(conn)
        files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "sql", "*.sql")))
        to_apply = [f for f in files if os.path.basename(f) not in already]
        if not to_apply:
            print("[v0] No new migrations.")
            return
        for f in to_apply:
            print("[v0] Applying:", os.path.basename(f))
            apply_sql(conn, f)
        print("[v0] Migrations complete.")

if __name__ == "__main__":
    main()
