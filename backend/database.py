import os
import shutil
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./expense_tracker.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)


def create_database_backup():
    """Create an automated rolling backup of SQLite database to prevent accidental data loss."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    db_file = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "").split("?")[0]
    if os.path.exists(db_file) and os.path.getsize(db_file) > 0:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = os.path.join(backup_dir, f"expense_tracker_backup_{timestamp}.db")
        shutil.copy2(db_file, backup_filename)
        # Keep latest 15 backups to prevent infinite disk growth
        existing_backups = sorted(
            [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("expense_tracker_backup_")],
            key=os.path.getmtime
        )
        if len(existing_backups) > 15:
            for old_b in existing_backups[:-15]:
                try:
                    os.remove(old_b)
                except OSError:
                    pass


# Enable SQLite Foreign Key constraints, WAL mode, and Account Immutability Triggers
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")

        # Guarantee Account Immutability:
        # Trigger 1: Disallow ANY deletion of user records
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_user_deletion
            BEFORE DELETE ON users
            BEGIN
                SELECT RAISE(ABORT, 'ACCOUNT IMMUTABILITY: User accounts cannot be deleted once created.');
            END;
        """)

        # Trigger 2: Disallow modification of core identity fields (id, email, created_at)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_user_identity_modification
            BEFORE UPDATE OF id, email, created_at ON users
            BEGIN
                SELECT RAISE(ABORT, 'ACCOUNT IMMUTABILITY: Immutable user identity fields (id, email, created_at) cannot be modified.');
            END;
        """)
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema_migrations():
    """Ensure newly added columns exist in SQLite database without losing any accounts or data."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            # Check users table
            tables = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchall()
            if tables:
                cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
                if "security_question" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN security_question VARCHAR(255)")
                if "security_answer_hash" not in cols:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN security_answer_hash VARCHAR(255)")

            # Create fixed_expenses table if not present
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS fixed_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(150) NOT NULL,
                    amount FLOAT NOT NULL DEFAULT 0.0,
                    is_variable_amount BOOLEAN NOT NULL DEFAULT 0,
                    frequency VARCHAR(20) NOT NULL DEFAULT 'monthly',
                    due_day INTEGER NOT NULL DEFAULT 1,
                    category VARCHAR(80) NOT NULL DEFAULT 'Bills & Utilities',
                    payment_mode VARCHAR(50) DEFAULT 'UPI',
                    notes VARCHAR(255),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    except Exception as e:
        # Avoid crashing if schema is already locked or handled elsewhere
        print(f"Schema migration notice: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


