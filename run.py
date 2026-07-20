import argparse
import sys
from pathlib import Path

from converter import ConversionError, convert_file

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare one BNGL model for MolClustPy."
    )
    parser.add_argument("model", type=Path)
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--validator", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()

def print_items(title: str, items: list[str]) -> None:
    if items:
        print(f"\n{title}")
        print("\n".join(f"- {item}" for item in items))

def main() -> int:
    args = parse_args()

    try:
        result = convert_file(
            args.model,
            run_validation=not args.skip_validation,
            validator=args.validator,
            force=args.force,
        )
    except (ConversionError, OSError) as error:
        print(f"Error: {error}")
        return 1

    print(f"Created: {result.output_file}")
    print_items("Changes", result.changes)
    print_items("Warnings", result.warnings)

    if result.validation_passed is True:
        print("\nValidation: passed")
    elif result.validation_passed is False:
        print("\nValidation: failed")
        print(result.validation_message)
        return 2
    elif not args.skip_validation:
        print("\nValidation: skipped")
        print(result.validation_message)

    return 0

if __name__ == "__main__":
    sys.exit(main())
