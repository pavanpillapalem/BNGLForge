import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SITE_NAME = "site"
VALIDATION_TIMEOUT = 120
EMPTY_MOLECULE = re.compile(r"\b([A-Za-z_]\w*)\s*\(\s*\)")
METHOD_ARGUMENT = re.compile(
    r"\bmethod\s*=>\s*(?:\"[^\"]*\"|'[^']*'|[^,\s}]+)",
    re.IGNORECASE,
)

class ConversionError(Exception):
    pass

@dataclass(slots=True)
class ConversionResult:
    output_file: Path
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_passed: bool | None = None
    validation_message: str = ""

def split_comment(line: str) -> tuple[str, str]:
    position = line.find("#")
    return (line, "") if position == -1 else (line[:position], line[position:])

def is_marker(line: str, marker: str) -> bool:
    code = split_comment(line)[0].strip().lower()
    marker = marker.lower()
    return code == marker or code.startswith(f"{marker} ")

def find_line(lines: list[str], marker: str) -> int | None:
    return next(
        (index for index, line in enumerate(lines) if is_marker(line, marker)),
        None,
    )

def find_block(
    lines: list[str], name: str, required: bool = True
) -> tuple[int, int] | None:
    start = find_line(lines, f"begin {name}")
    if start is not None:
        for end in range(start + 1, len(lines)):
            if is_marker(lines[end], f"end {name}"):
                return start, end

    if required:
        raise ConversionError(f"Missing 'begin {name}' or 'end {name}'.")
    return None

def replace_empty_molecules(lines: list[str]) -> int:
    molecule_types = find_block(lines, "molecule types")
    model = find_block(lines, "model")
    assert molecule_types is not None and model is not None

    empty_names = {
        match.group(1)
        for line in lines[molecule_types[0] + 1 : molecule_types[1]]
        for match in EMPTY_MOLECULE.finditer(split_comment(line)[0])
    }

    if not empty_names:
        return 0

    actions = find_block(lines, "actions", required=False)
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        name = match.group(1)
        if name not in empty_names:
            return match.group(0)
        replacements += 1
        return f"{name}({SITE_NAME})"

    for index in range(model[0] + 1, model[1]):
        if actions and actions[0] <= index <= actions[1]:
            continue
        code, comment = split_comment(lines[index])
        lines[index] = EMPTY_MOLECULE.sub(replace, code) + comment

    return replacements

def mask_comments(text: str) -> str:
    masked = []
    for line in text.splitlines(keepends=True):
        code, comment = split_comment(line)
        masked.append(
            code + "".join("\n" if char == "\n" else " " for char in comment)
        )
    return "".join(masked)

def find_identifier(text: str, name: str, start: int = 0) -> int:
    pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    match = pattern.search(text, start)
    return -1 if match is None else match.start()

def find_call_end(text: str, opening: int) -> int | None:
    depth = 0
    quote = None
    escaped = False

    for index in range(opening, len(text)):
        character = text[index]

        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue

        if character in "'\"":
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index + 1

    return None

def find_call(text: str, name: str) -> str | None:
    visible = mask_comments(text)
    search_from = 0

    while True:
        start = find_identifier(visible, name, search_from)
        if start == -1:
            return None

        opening = start + len(name)
        while opening < len(visible) and visible[opening].isspace():
            opening += 1

        if opening < len(visible) and visible[opening] == "(":
            end = find_call_end(visible, opening)
            if end is not None:
                return text[start:end]

        search_from = start + len(name)

def set_nf_method(simulate_call: str) -> str:
    if METHOD_ARGUMENT.search(simulate_call):
        return METHOD_ARGUMENT.sub('method=>"nf"', simulate_call, count=1)

    opening_brace = simulate_call.find("{")
    if opening_brace == -1:
        return simulate_call

    return (
        simulate_call[: opening_brace + 1]
        + 'method=>"nf", '
        + simulate_call[opening_brace + 1 :]
    )

def rewrite_actions(lines: list[str]) -> bool:
    model = find_block(lines, "model")
    actions = find_block(lines, "actions", required=False)
    assert model is not None

    if actions:
        action_text = "".join(lines[actions[0] + 1 : actions[1]])
        del lines[actions[0] : actions[1] + 1]
        model = find_block(lines, "model")
        assert model is not None
    else:
        action_text = "".join(lines[model[1] + 1 :])

    simulate = find_call(action_text, "simulate")
    new_suffix = ["\nwriteXML()\n"]

    if simulate:
        new_suffix.append(set_nf_method(simulate).strip() + "\n")

    lines[model[1] + 1 :] = new_suffix
    return simulate is not None

def validator_command(validator: str | Path | None) -> list[str] | None:
    if validator:
        path = str(Path(validator).expanduser().resolve())
        return ["perl", path] if path.lower().endswith(".pl") else [path]

    bng2 = shutil.which("BNG2.pl")
    if bng2:
        return ["perl", bng2]

    bionetgen = shutil.which("bionetgen")
    return [bionetgen, "run", "-i"] if bionetgen else None

def validate_bngl(
    bngl_file: Path, validator: str | Path | None = None
) -> tuple[bool | None, str]:
    command = validator_command(validator)
    if command is None:
        return None, "BioNetGen not found. Use --validator or --skip-validation."

    with tempfile.TemporaryDirectory(prefix="bnglforge_") as folder:
        copied_file = Path(folder) / bngl_file.name
        shutil.copy2(bngl_file, copied_file)

        try:
            completed = subprocess.run(
                [*command, str(copied_file)],
                cwd=folder,
                text=True,
                capture_output=True,
                timeout=VALIDATION_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "BioNetGen validation timed out."
        except OSError as error:
            return False, f"Could not start BioNetGen: {error}"

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    message = "\n\n".join(
        part
        for part in (
            f"STDOUT:\n{stdout}" if stdout else "",
            f"STDERR:\n{stderr}" if stderr else "",
        )
        if part
    )
    reported_error = any(
        line.strip().startswith(("error", "fatal")) or "syntax error" in line
        for line in f"{stdout}\n{stderr}".lower().splitlines()
    )

    if completed.returncode != 0 or reported_error:
        return False, message or "BioNetGen validation failed."
    return True, message or "BioNetGen validation passed."

def convert_file(
    input_file: str | Path,
    *,
    run_validation: bool = True,
    validator: str | Path | None = None,
    force: bool = False,
) -> ConversionResult:
    source = Path(input_file).expanduser().resolve()

    if not source.is_file():
        raise ConversionError(f"File not found: {source}")
    if source.suffix.lower() != ".bngl":
        raise ConversionError("Input must be a .bngl file.")
    if source.stem.endswith("_molclustpy"):
        raise ConversionError("Use the original BNGL file.")

    output = source.with_name(f"{source.stem}_molclustpy.bngl")
    if output.exists() and not force:
        raise ConversionError(f"{output.name} already exists. Use --force.")

    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    changes = []
    warnings = []

    replacements = replace_empty_molecules(lines)
    if replacements:
        changes.append(f"Added placeholder sites in {replacements} location(s).")

    has_simulation = rewrite_actions(lines)
    changes.append("Replaced actions with writeXML() and NFsim.")
    if not has_simulation:
        warnings.append("No simulate(...) action was found.")

    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text("".join(lines).rstrip() + "\n", encoding="utf-8")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    result = ConversionResult(output, changes, warnings)

    if run_validation:
        result.validation_passed, result.validation_message = validate_bngl(
            output, validator
        )

        if result.validation_passed is False:
            failed = output.with_name(
                f"{source.stem}_molclustpy_FAILED_VALIDATION.bngl"
            )
            failed.unlink(missing_ok=True)
            output.replace(failed)
            result.output_file = failed

    return result
