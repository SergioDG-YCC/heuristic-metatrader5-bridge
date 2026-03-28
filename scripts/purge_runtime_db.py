"""
Purge Runtime DB - Reset to clean state

Usage:
    python scripts/purge_runtime_db.py

This will:
- Delete all data from runtime.db
- Keep table structure intact
- Allow fresh start on next backend launch
"""
import sqlite3
from pathlib import Path

def get_db_path() -> Path:
    """Get runtime.db path from .env or default."""
    env_file = Path(__file__).parent.parent / ".env"
    db_path = Path(__file__).parent.parent / "storage" / "runtime.db"
    
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("RUNTIME_DB_PATH="):
                db_path = Path(line.split("=", 1)[1].strip())
                break
    
    return db_path


def purge_database(db_path: Path) -> None:
    """Delete all data from runtime.db."""
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return
    
    print(f"Purging database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
    """)
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"Found {len(tables)} tables")
    
    # Delete all data from each table
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"  ✓ Purged: {table}")
        except Exception as e:
            print(f"  ✗ Failed to purge {table}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\nDatabase purged successfully!")
    print(f"Restart backend to reinitialize with clean state.")


if __name__ == "__main__":
    db_path = get_db_path()
    purge_database(db_path)
