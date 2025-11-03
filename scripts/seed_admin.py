import os
import psycopg
from passlib.context import CryptContext

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/erp")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def main():
    email = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("SEED_ADMIN_PASSWORD", "admin123")
    full_name = os.environ.get("SEED_ADMIN_NAME", "Admin")

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(1) from users")
            count = cur.fetchone()[0]
            if count > 0:
                print("[v0] Users already exist; skipping admin seed.")
                return
            hashed = pwd_context.hash(password)
            cur.execute(
                "insert into users (email, password_hash, role, full_name) values (%s, %s, 'admin', %s)",
                (email, hashed, full_name),
            )
            print(f"[v0] Seeded admin user: {email}")

if __name__ == "__main__":
    main()
