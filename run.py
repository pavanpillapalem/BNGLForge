import argparse
import sys
from converter import ConversionError, convert_file

def main():
    parser = argparse.ArgumentParser(description="Convert BNGL for MolClustPy.")
    parser.add_argument("input_file", help="Source .bngl file")
    parser.add_argument("-f", "--force", action="store_true",
                        help="Replace existing output")
    args = parser.parse_args()

    try:
        result = convert_file(args.input_file, args.force)
    except (ConversionError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Created: {result.output_file}")
    for heading, items in (("Changes", result.changes),
                           ("Warnings", result.warnings)):
        if items:
            print(f"\n{heading}:")
            for item in items: print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
