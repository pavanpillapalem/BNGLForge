import sys
from pathlib import Path

from converter import ConversionError
from converter import convert_file


def has_flag(metadata, flag):
    for line in metadata.read_text().splitlines():
        line = line.split("#", 1)[0]
        line = line.strip().lower()

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        if key.strip() == flag:
            return value.strip() == "true"

    return False


def main():
    arguments = sys.argv[1:]

    if not arguments:
        print(
            "Use: python metadata_compatibility.py "
            "<folder> -molclustpy"
        )
        return

    folder = Path(arguments[0]).resolve()
    use_mcp = "-molclustpy" in arguments
    use_nfsim = "-nfsim" in arguments

    if use_mcp == use_nfsim:
        print("Use exactly one flag:")
        print("-molclustpy or -nfsim")
        return

    if not folder.is_dir():
        print("Folder not found:", folder)
        return

    metadata = folder / "metadata.yaml"

    if not metadata.is_file():
        print("metadata.yaml not found.")
        return

    if use_mcp:
        flag = "molclustpy_compatible"
    else:
        flag = "nfsim_compatible"

    if not has_flag(metadata, flag):
        print(flag + " is not true.")
        return

    models = []

    for model in folder.glob("*.bngl"):
        if not model.stem.endswith("_molclustpy"):
            models.append(model)

    if len(models) == 0:
        print("No BNGL file found.")
        return

    if len(models) > 1:
        print("More than one BNGL file found.")
        return

    try:
        result = convert_file(
            models[0],
            run_validation=False,
        )
        print("Created:", result.output_file)

    except ConversionError as error:
        print("Conversion failed:")
        print(error)


if __name__ == "__main__":
    main()
