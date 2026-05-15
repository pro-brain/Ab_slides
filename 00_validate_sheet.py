"""
00_validate_sheet.py — Validate a raw Ab3D screening sheet (CSV exported from Google Sheets)
before running the conversion pipeline. Collects all issues and prints them grouped by
severity. Exits with code 1 if any errors are found; exits 0 if only warnings (or clean).

Usage
-----
  python 00_validate_sheet.py params.toml          # reads ab3d_sheet path from params file
  python 00_validate_sheet.py params.json
  python 00_validate_sheet.py --sheet sheet.csv    # pass CSV path directly

What it checks
--------------
  ERROR  (exit 1):
    1. Required columns present:
         'Czi Filename', 'Scene 1' … 'Scene 6'
    2. 'Czi Filename' prefix is exactly 'Ab3D-' (case-sensitive).
         Catches typos like 'Ab3d-', 'ab3d-', 'AB3D-', etc.

  WARNING (exit 0):
    3. 'Czi Filename' is missing the .czi extension.
         Filenames without an extension are handled downstream by 01_convert.py,
         but this warning prompts the user to fix the sheet.
    4. Scene name auto-increment variants detected.
         Groups scene names by text-before-trailing-digits; flags rows whose
         numeric suffix differs from the batch majority — likely caused by
         Google Sheets auto-incrementing on copy/paste
         (e.g. 'Hu-JC7/8/10' when 106 rows correctly say 'Hu-JC7/8/9').
"""
import pandas as pd
import re
import os
import sys

SCENE_COLUMNS = ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 4', 'Scene 5', 'Scene 6']
REQUIRED_COLUMNS = ['Czi Filename'] + SCENE_COLUMNS


def load_sheet(sheet_path):
    return pd.read_csv(sheet_path, dtype=str)


def check_required_columns(df):
    errors = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    for c in missing:
        errors.append(f"ERROR: Required column missing: '{c}'")
    return errors


def check_filename_prefix(df):
    """Check that all non-empty Czi Filename values start with exactly 'Ab3D-' (case-sensitive)."""
    errors = []
    col = 'Czi Filename'
    for idx, row in df.iterrows():
        val = row.get(col)
        if pd.isna(val) or str(val).strip() == '':
            continue
        val = str(val).strip()
        if not re.match(r'^Ab3D-', val):
            errors.append(
                f"ERROR: Row {idx+2}: 'Czi Filename' has wrong prefix "
                f"(expected 'Ab3D-'): '{val}'"
            )
    return errors


def check_filename_extension(df):
    """Warn about Czi Filename values that are missing the .czi extension."""
    warnings = []
    col = 'Czi Filename'
    for idx, row in df.iterrows():
        val = row.get(col)
        if pd.isna(val) or str(val).strip() == '':
            continue
        val = str(val).strip()
        if not val.lower().endswith('.czi'):
            warnings.append(
                f"WARNING: Row {idx+2}: 'Czi Filename' missing .czi extension: '{val}'"
            )
    return warnings


def check_scene_autoincrement(df):
    """
    Detect Google Sheets auto-incremented scene names.

    Groups scene name values by their text-before-trailing-digits prefix.
    Within each prefix group, the numeric suffix used by the majority of rows is
    considered correct; minority variants are flagged as likely auto-increment accidents.

    Example: if 95 rows have 'Hu-JC7/8/9' but 2 rows have 'Hu-JC7/8/10',
    those 2 rows are flagged.
    """
    warnings = []

    pattern = re.compile(r'^(.+?)(\d+)$')
    # prefix -> {suffix_str -> list of (row_num, col_name, full_value)}
    groups = {}

    for idx, row in df.iterrows():
        for col in SCENE_COLUMNS:
            if col not in df.columns:
                continue
            val = row.get(col)
            if pd.isna(val) or str(val).strip() == '':
                continue
            val = str(val).strip()
            m = pattern.match(val)
            if m:
                prefix, suffix = m.group(1), m.group(2)
                groups.setdefault(prefix, {}).setdefault(suffix, []).append(
                    (idx + 2, col, val)  # +2: 1-based row index + header row
                )

    for prefix, suffix_map in groups.items():
        if len(suffix_map) <= 1:
            continue  # all rows agree on the suffix — no problem
        majority_suffix = max(suffix_map, key=lambda s: len(suffix_map[s]))
        for suffix, occurrences in suffix_map.items():
            if suffix == majority_suffix:
                continue
            majority_val = f"{prefix}{majority_suffix}"
            majority_count = len(suffix_map[majority_suffix])
            for row_num, col_name, scene_val in occurrences:
                warnings.append(
                    f"WARNING: Row {row_num}, {col_name}: scene name '{scene_val}' "
                    f"looks like an auto-increment of '{majority_val}' "
                    f"({majority_count} rows use '{majority_val}')"
                )
    return warnings


def validate(sheet_path):
    df = load_sheet(sheet_path)

    all_errors = []
    all_warnings = []

    col_errors = check_required_columns(df)
    all_errors.extend(col_errors)

    if not col_errors:  # only run row-level checks if required columns exist
        all_errors.extend(check_filename_prefix(df))
        all_warnings.extend(check_filename_extension(df))
        all_warnings.extend(check_scene_autoincrement(df))

    for msg in all_errors:
        print(msg)
    for msg in all_warnings:
        print(msg)

    n_err = len(all_errors)
    n_warn = len(all_warnings)
    if n_err == 0 and n_warn == 0:
        print("Validation passed.")
    else:
        print(f"\n{n_err} error(s), {n_warn} warning(s) found.")

    return n_err


if __name__ == '__main__':
    import argparse
    import json
    import tomllib as tomli

    parser = argparse.ArgumentParser(
        description='Validate an Ab3D screening sheet for common input errors.\n\n'
                    'Usage:\n'
                    '  python 00_validate_sheet.py params.toml\n'
                    '  python 00_validate_sheet.py --sheet path/to/sheet.csv'
    )
    parser.add_argument(
        'params', nargs='?',
        help='Path to JSON or TOML params file (must contain ab3d_sheet key)'
    )
    parser.add_argument(
        '--sheet',
        help='Path to Ab3D screening CSV directly (alternative to params file)'
    )
    args = parser.parse_args()

    if args.sheet:
        sheet_path = args.sheet
    elif args.params:
        params_path = args.params
        if params_path.endswith('.json'):
            with open(params_path, 'r') as f:
                params = json.load(f)
        elif params_path.endswith('.toml'):
            with open(params_path, 'rb') as f:
                params = tomli.load(f)
        else:
            print("Error: params file must be .json or .toml")
            sys.exit(2)
        sheet_path = params.get('ab3d_sheet')
        if not sheet_path:
            print("Error: 'ab3d_sheet' key not found in params file.")
            sys.exit(2)
    else:
        parser.print_help()
        sys.exit(2)

    if not os.path.isfile(sheet_path):
        print(f"Error: Sheet file not found: {sheet_path}")
        sys.exit(2)

    n_errors = validate(sheet_path)
    sys.exit(1 if n_errors > 0 else 0)
