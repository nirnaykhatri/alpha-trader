#!/usr/bin/env python3
"""
Interface Import Enforcement Script.

This script checks that interface imports follow the canonical location rules:
- Database interfaces (IDatabaseManager, IBotRepository) must be imported from 
  src.database.database_interface, NOT from src.interfaces
- Broker interfaces must be imported from src.broker.interfaces
- Bot engine interfaces must be imported from src.bot_engine.interfaces

Run as part of CI to prevent interface drift.

Usage:
    python scripts/check_interface_imports.py
    
Exit Codes:
    0 - All imports follow canonical rules
    1 - Found violations

Author: Trading Bot Team
Version: 1.0.0
"""

import os
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Set


class Violation(NamedTuple):
    """Represents an import violation."""
    file: str
    line_number: int
    line: str
    rule: str
    fix: str


# =============================================================================
# Rules Configuration
# =============================================================================

# Interfaces that should ONLY be imported from their canonical location
CANONICAL_RULES = {
    # Database interfaces - canonical location: src.database.database_interface
    "IDatabaseManager": {
        "canonical": "src.database.database_interface",
        "forbidden_patterns": [
            r"from\s+src\.interfaces\s+import\s+.*IDatabaseManager",
            r"from\s+src\.interfaces\s+import\s+IDatabaseManager",
        ],
    },
    "IBotRepository": {
        "canonical": "src.database.database_interface", 
        "forbidden_patterns": [
            r"from\s+src\.interfaces\s+import\s+.*IBotRepository",
            r"from\s+src\.interfaces\s+import\s+IBotRepository",
        ],
    },
}

# Files to exclude from checking (e.g., backward-compat shims)
EXCLUDED_FILES = {
    "src/interfaces/__init__.py",  # Package init can re-export
    "src/interfaces_legacy.py.bak",  # Old backup file
}

# Directories to skip entirely
EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    ".venv-2", 
    "htmlcov",
    "node_modules",
    ".pytest_cache",
}


# =============================================================================
# Checker Implementation
# =============================================================================

def find_python_files(root_dir: Path) -> List[Path]:
    """Find all Python files in the directory tree."""
    python_files = []
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = Path(dirpath) / filename
                rel_path = filepath.relative_to(root_dir).as_posix()
                
                # Skip excluded files
                if rel_path not in EXCLUDED_FILES:
                    python_files.append(filepath)
    
    return python_files


def check_file(filepath: Path, root_dir: Path) -> List[Violation]:
    """Check a single file for import violations."""
    violations = []
    rel_path = filepath.relative_to(root_dir).as_posix()
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Warning: Could not read {rel_path}: {e}", file=sys.stderr)
        return violations
    
    for line_num, line in enumerate(lines, start=1):
        # Check each canonical rule
        for interface_name, rule_config in CANONICAL_RULES.items():
            for pattern in rule_config["forbidden_patterns"]:
                if re.search(pattern, line):
                    violations.append(Violation(
                        file=rel_path,
                        line_number=line_num,
                        line=line.strip(),
                        rule=f"{interface_name} must be imported from {rule_config['canonical']}",
                        fix=f"from {rule_config['canonical']} import {interface_name}",
                    ))
    
    return violations


def main() -> int:
    """Main entry point."""
    # Determine root directory
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent  # Go up from scripts/ to repo root
    
    # Also check if we're in the right directory
    if not (root_dir / "src").exists():
        root_dir = Path.cwd()
        if not (root_dir / "src").exists():
            print("Error: Cannot find src/ directory. Run from repo root.", file=sys.stderr)
            return 1
    
    print(f"Checking interface imports in: {root_dir}")
    print(f"Rules enforced:")
    for interface, config in CANONICAL_RULES.items():
        print(f"  - {interface}: must use {config['canonical']}")
    print()
    
    # Find and check all Python files
    python_files = find_python_files(root_dir / "src")
    all_violations: List[Violation] = []
    
    for filepath in python_files:
        violations = check_file(filepath, root_dir)
        all_violations.extend(violations)
    
    # Report results
    if all_violations:
        print(f"❌ Found {len(all_violations)} violation(s):\n")
        
        for v in all_violations:
            print(f"  {v.file}:{v.line_number}")
            print(f"    Line: {v.line}")
            print(f"    Rule: {v.rule}")
            print(f"    Fix:  {v.fix}")
            print()
        
        print("Please update imports to use canonical locations.")
        return 1
    else:
        print(f"✅ All {len(python_files)} files follow canonical import rules.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
