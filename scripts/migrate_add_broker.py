#!/usr/bin/env python3
"""
Database Migration: Add broker column to tables.

This migration adds the 'broker' column to positions, orders, and trades tables
to support multi-broker functionality.
"""

import sqlite3
import sys
from pathlib import Path


def migrate_database(db_path: str = "trading_bot.db") -> bool:
    """
    Add broker column to database tables.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        True if migration successful, False otherwise
    """
    if not Path(db_path).exists():
        print(f"Database file not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables_to_update = ['positions', 'orders', 'trades']
    
    for table in tables_to_update:
        try:
            # Check if column already exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'broker' in columns:
                print(f"✓ {table}: broker column already exists")
            else:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN broker TEXT DEFAULT 'alpaca'")
                print(f"✓ {table}: added broker column")
        except sqlite3.OperationalError as e:
            print(f"✗ {table}: {e}")
    
    conn.commit()
    conn.close()
    
    print("\nMigration complete!")
    return True


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "trading_bot.db"
    success = migrate_database(db_path)
    sys.exit(0 if success else 1)
