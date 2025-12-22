#!/usr/bin/env python3
"""
Schema Validation Script

Validates JSON data against JSON Schema definitions.
Can be used to validate individual files or all sample files.

Usage:
    python scripts/validate_schema_samples.py
    python scripts/validate_schema_samples.py <schema_file> <data_file>

Examples:
    # Validate all samples
    python scripts/validate_schema_samples.py

    # Validate specific file
    python scripts/validate_schema_samples.py schemas/raw_event.v1.json schemas/samples/raw_event_valid.json
"""

import json
import sys
from pathlib import Path
from typing import Tuple

try:
    import jsonschema
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    print("Error: jsonschema package not installed")
    print("Install with: pip install jsonschema")
    sys.exit(1)


def load_json(file_path: Path) -> dict:
    """Load JSON from file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_data(schema: dict, data: dict, schema_name: str, data_name: str) -> Tuple[bool, str]:
    """Validate data against schema."""
    try:
        validator = Draft202012Validator(schema)
        validator.validate(data)
        return True, f"✓ {data_name} is valid against {schema_name}"
    except ValidationError as e:
        error_path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        return False, f"✗ {data_name} validation failed:\n  Path: {error_path}\n  Error: {e.message}"
    except Exception as e:
        return False, f"✗ Unexpected error validating {data_name}: {str(e)}"


def validate_all_samples(repo_root: Path) -> int:
    """Validate all sample files against their corresponding schemas."""
    schemas_dir = repo_root / "schemas"
    samples_dir = schemas_dir / "samples"
    
    if not samples_dir.exists():
        print(f"Error: Samples directory not found: {samples_dir}")
        return 1
    
    # Define schema-sample pairs
    validations = [
        ("raw_event.v1.json", "raw_event_valid.json"),
        ("normalized_event.v1.json", "normalized_event_valid.json"),
    ]
    
    print("Validating schema samples...\n")
    all_passed = True
    
    for schema_file, sample_file in validations:
        schema_path = schemas_dir / schema_file
        sample_path = samples_dir / sample_file
        
        if not schema_path.exists():
            print(f"✗ Schema not found: {schema_path}")
            all_passed = False
            continue
        
        if not sample_path.exists():
            print(f"✗ Sample not found: {sample_path}")
            all_passed = False
            continue
        
        try:
            schema = load_json(schema_path)
            data = load_json(sample_path)
            
            passed, message = validate_data(schema, data, schema_file, sample_file)
            print(message)
            
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"✗ Error processing {schema_file} / {sample_file}: {str(e)}")
            all_passed = False
    
    print()
    if all_passed:
        print("All validations passed! ✓")
        return 0
    else:
        print("Some validations failed! ✗")
        return 1


def validate_specific(schema_path: Path, data_path: Path) -> int:
    """Validate a specific data file against a schema."""
    if not schema_path.exists():
        print(f"Error: Schema file not found: {schema_path}")
        return 1
    
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        return 1
    
    try:
        schema = load_json(schema_path)
        data = load_json(data_path)
        
        passed, message = validate_data(
            schema, data, 
            schema_path.name, 
            data_path.name
        )
        print(message)
        
        return 0 if passed else 1
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def main():
    """Main entry point."""
    # Determine repository root (assuming script is in scripts/ directory)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    if len(sys.argv) == 1:
        # No arguments - validate all samples
        return validate_all_samples(repo_root)
    elif len(sys.argv) == 3:
        # Two arguments - validate specific files
        schema_path = Path(sys.argv[1])
        data_path = Path(sys.argv[2])
        
        # Make paths absolute if relative
        if not schema_path.is_absolute():
            schema_path = repo_root / schema_path
        if not data_path.is_absolute():
            data_path = repo_root / data_path
        
        return validate_specific(schema_path, data_path)
    else:
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
