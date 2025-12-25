#!/usr/bin/env python3
"""
Type Generation Script - Syncs Python enums to TypeScript types.

This script reads Python enum definitions from src/domain/bot_enums.py
and generates corresponding TypeScript types to ensure frontend/backend
type consistency.

Usage:
    python scripts/generate_typescript_types.py
    
    # Or with specific output path
    python scripts/generate_typescript_types.py --output trading-terminal/lib/types/generated-bot-types.ts

Output:
    Creates a TypeScript file with equivalent type definitions
    that should be imported by the frontend codebase.

Author: Trading Bot Team
Version: 1.0.0
"""

import argparse
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple


def parse_python_enum(enum_content: str, enum_name: str) -> List[Tuple[str, str]]:
    """
    Parse Python Enum members from class content.
    
    Args:
        enum_content: The content of the enum class
        enum_name: Name of the enum class
        
    Returns:
        List of (member_name, value) tuples
    """
    members = []
    # Match patterns like: MEMBER = "value" or MEMBER = 5
    pattern = r'^\s*([A-Z_][A-Z0-9_]*)\s*=\s*["\']?([^"\'#\n]+)["\']?'
    
    for line in enum_content.split('\n'):
        match = re.match(pattern, line)
        if match:
            name, value = match.groups()
            value = value.strip().strip('"\'')
            members.append((name, value))
    
    return members


def extract_enums_from_file(filepath: Path) -> Dict[str, List[Tuple[str, str]]]:
    """
    Extract all Enum classes from a Python file.
    
    Args:
        filepath: Path to Python file
        
    Returns:
        Dictionary mapping enum name to list of (member, value) tuples
    """
    content = filepath.read_text()
    enums = {}
    
    # Match class definitions that inherit from Enum
    class_pattern = r'class\s+(\w+)\s*\(\s*(?:str,\s*)?Enum\s*\):\s*(?:"""[^"]*""")?'
    
    # Find all enum classes
    class_matches = list(re.finditer(class_pattern, content))
    
    for i, match in enumerate(class_matches):
        enum_name = match.group(1)
        start = match.end()
        
        # Find the end of this class (start of next class or end of file)
        if i + 1 < len(class_matches):
            end = class_matches[i + 1].start()
        else:
            # Find next class definition that's not an Enum
            next_class = re.search(r'\nclass\s+\w+', content[start:])
            if next_class:
                end = start + next_class.start()
            else:
                end = len(content)
        
        enum_content = content[start:end]
        members = parse_python_enum(enum_content, enum_name)
        
        if members:
            enums[enum_name] = members
    
    return enums


def python_to_typescript_name(python_name: str) -> str:
    """Convert PythonEnumName to pythonEnumName for TypeScript."""
    if not python_name:
        return python_name
    return python_name[0].lower() + python_name[1:]


def generate_typescript(enums: Dict[str, List[Tuple[str, str]]]) -> str:
    """
    Generate TypeScript type definitions from Python enums.
    
    Args:
        enums: Dictionary of enum name to members
        
    Returns:
        TypeScript type definition string
    """
    lines = [
        "/**",
        " * Auto-generated TypeScript types from Python enums.",
        f" * Generated at: {datetime.now().isoformat()}",
        " * Source: src/domain/bot_enums.py",
        " * ",
        " * DO NOT EDIT MANUALLY - Run `python scripts/generate_typescript_types.py`",
        " * to regenerate this file.",
        " */",
        "",
    ]
    
    for enum_name, members in enums.items():
        # Generate union type
        ts_name = enum_name
        
        # Build comment
        lines.append(f"/**")
        lines.append(f" * TypeScript equivalent of Python {enum_name} enum")
        lines.append(f" */")
        
        # Generate type union
        if all(isinstance(m[1], str) and not m[1].isdigit() for m in members):
            # String enum - generate union type
            values = " | ".join(f"'{m[1]}'" for m in members)
            lines.append(f"export type {ts_name} = {values}")
        else:
            # Numeric or mixed - generate const enum
            lines.append(f"export const {ts_name} = {{")
            for name, value in members:
                if value.isdigit():
                    lines.append(f"  {name}: {value},")
                else:
                    lines.append(f"  {name}: '{value}',")
            lines.append("} as const")
            lines.append(f"export type {ts_name} = typeof {ts_name}[keyof typeof {ts_name}]")
        
        lines.append("")
        
        # Generate mapping object for display labels
        lines.append(f"/**")
        lines.append(f" * Display labels for {enum_name}")
        lines.append(f" */")
        lines.append(f"export const {ts_name.upper()}_LABELS: Record<{ts_name}, string> = {{")
        for name, value in members:
            # Convert SNAKE_CASE to Title Case for display
            label = name.replace('_', ' ').title()
            lines.append(f"  '{value}': '{label}',")
        lines.append("}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    """Main entry point for type generation."""
    parser = argparse.ArgumentParser(
        description="Generate TypeScript types from Python enums"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("src/domain/bot_enums.py"),
        help="Source Python file with enum definitions"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trading-terminal/lib/types/generated-bot-types.ts"),
        help="Output TypeScript file path"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output instead of writing to file"
    )
    
    args = parser.parse_args()
    
    # Validate source file exists
    if not args.source.exists():
        print(f"Error: Source file not found: {args.source}", file=sys.stderr)
        sys.exit(1)
    
    print(f"📖 Reading enums from: {args.source}")
    enums = extract_enums_from_file(args.source)
    
    print(f"   Found {len(enums)} enums:")
    for name, members in enums.items():
        print(f"   - {name}: {len(members)} members")
    
    # Generate TypeScript
    typescript_content = generate_typescript(enums)
    
    if args.dry_run:
        print("\n--- Generated TypeScript ---")
        print(typescript_content)
    else:
        # Ensure output directory exists
        args.output.parent.mkdir(parents=True, exist_ok=True)
        
        # Write output file
        args.output.write_text(typescript_content)
        print(f"✅ Generated TypeScript types: {args.output}")
        print(f"   Import in frontend: import {{ BotType, BotState, ... }} from '@/lib/types/generated-bot-types'")


if __name__ == "__main__":
    main()
