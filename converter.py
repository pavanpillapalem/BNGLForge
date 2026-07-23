import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
SITE = "site"
PATTERN_BLOCKS = ("molecule types", "seed species", "species",
                  "observables", "reaction rules")
class ConversionError(Exception):
    pass
class ConversionResult:
    def __init__(self, output_file):
        self.output_file = output_file
        self.changes, self.warnings = [], []

def split_comment(line):
    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    raw = line[:-len(ending)] if ending else line
    quote, escaped = None, False
    for index, char in enumerate(raw):
        if quote:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == quote: quote = None
        elif char in "'\"":
            quote = char
        elif char == "#":
            return raw[:index], raw[index:], ending
    return raw, "", ending

def mask_comments_and_quotes(text):
    output = []
    for line in text.splitlines(keepends=True):
        code, comment, ending = split_comment(line)
        masked, quote, escaped = list(code), None, False
        for index, char in enumerate(code):
            if quote:
                masked[index] = " "
                if escaped: escaped = False
                elif char == "\\": escaped = True
                elif char == quote: quote = None
            elif char in "'\"":
                quote, masked[index] = char, " "
        output.append("".join(masked) + " " * len(comment) + ending)
    return "".join(output)

def find_block(text, name):
    opening, closing = f"begin {name.lower()}", f"end {name.lower()}"
    start = body = None
    pos = 0
    for line in text.splitlines(keepends=True):
        end = pos + len(line)
        code, _, _ = split_comment(line)
        clean = " ".join(code.strip().lower().split())
        if start is None and (clean == opening or clean.startswith(opening + " ")):
            start, body = pos, end
        elif start is not None and (clean == closing or clean.startswith(closing + " ")):
            return start, end, body, pos
        pos = end
    return None

def seed_block(text):
    return find_block(text, "seed species") or find_block(text, "species")

def replace_empty_sites(text, changes):
    block = find_block(text, "molecule types")
    if not block: raise ConversionError("Missing 'molecule types' block.")
    call = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*\(\s*\)")
    names = set()
    for line in text[block[2]:block[3]].splitlines(keepends=True):
        code, _, _ = split_comment(line)
        names.update(match.group(1) for match in call.finditer(code))
    counts = {name: 0 for name in names}

    for block_name in PATTERN_BLOCKS:
        block = find_block(text, block_name)
        if not block: continue
        output = []
        for line in text[block[2]:block[3]].splitlines(keepends=True):
            code, comment, ending = split_comment(line)
            for name in names:
                pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}\s*\(\s*\)")
                code, count = pattern.subn(f"{name}({SITE})", code)
                counts[name] += count
            output.append(code + comment + ending)
        text = text[:block[2]] + "".join(output) + text[block[3]:]

    for name, count in sorted(counts.items()):
        if count:
            changes.append(f"Changed {name}() to {name}({SITE}) in {count} place(s).")
    return text

def number(value):
    try: return Decimal(value)
    except InvalidOperation: return None

def identifier(value):
    return re.fullmatch(r"[A-Za-z_]\w*", value) is not None

def replace_last(code, value):
    match = re.search(r"\S+(?=\s*$)", code)
    return code[:match.start()] + value + code[match.end():]

def fix_populations(text, changes, warnings):
    block = seed_block(text)
    if not block: raise ConversionError("Missing 'seed species' or 'species' block.")
    base = text.count("\n", 0, block[2]) + 1
    errors, refs, output = [], set(), []

    for offset, line in enumerate(text[block[2]:block[3]].splitlines(keepends=True)):
        code, comment, ending = split_comment(line)
        tokens = code.split()
        if len(tokens) < 2:
            output.append(line); continue
        value, line_no = tokens[-1], base + offset
        num = number(value)

        if num is not None:
            if not num.is_finite() or num < 0 or num != num.to_integral_value():
                errors.append(f"Line {line_no}: species population '{value}' is not a nonnegative integer.")
            else:
                fixed = str(int(num))
                if fixed != value:
                    code = replace_last(code, fixed)
                    changes.append(f"Changed species population {value} to {fixed} on line {line_no}.")
        elif identifier(value):
            refs.add(value)
        else:
            warnings.append(f"Line {line_no}: could not verify species population '{value}'.")
        output.append(code + comment + ending)

    text = text[:block[2]] + "".join(output) + text[block[3]:]
    if errors: raise ConversionError("Population validation failed:\n" + "\n".join(errors))
    return fix_population_parameters(text, refs, changes, warnings)

def fix_population_parameters(text, refs, changes, warnings):
    if not refs: return text
    block = find_block(text, "parameters")
    if not block:
        raise ConversionError("Species use parameter populations, but the 'parameters' block is missing.")

    pattern = re.compile(r"^(\s*)([A-Za-z_]\w*)(?:(\s*=\s*)|(\s+))(\S+)(.*)$")
    base = text.count("\n", 0, block[2]) + 1
    errors, found, output = [], set(), []

    for offset, line in enumerate(text[block[2]:block[3]].splitlines(keepends=True)):
        code, comment, ending = split_comment(line)
        line_no = base + offset
        match = pattern.match(code)
        if not match or match.group(2) not in refs:
            output.append(line); continue

        name, value = match.group(2), match.group(5)
        found.add(name); num = number(value)
        if num is None:
            warnings.append(f"Line {line_no}: could not verify population parameter {name}='{value}'.")
        elif not num.is_finite() or num < 0 or num != num.to_integral_value():
            errors.append(f"Line {line_no}: population parameter {name}={value} is not a nonnegative integer.")
        else:
            fixed = str(int(num))
            if fixed != value:
                code = code[:match.start(5)] + fixed + code[match.end(5):]
                changes.append(f"Changed population parameter {name} from {value} to {fixed}.")
        output.append(code + comment + ending)

    for name in sorted(refs - found):
        warnings.append(f"Species population references '{name}', but that parameter was not found.")
    if errors: raise ConversionError("Population validation failed:\n" + "\n".join(errors))
    return text[:block[2]] + "".join(output) + text[block[3]:]

def closing_paren(text, opening):
    depth = 0
    for i in range(opening, len(text)):
        if text[i] == "(": depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0: return i + 1
    return None

def find_call(text, name, start=0, end=None):
    end = len(text) if end is None else end
    masked = mask_comments_and_quotes(text)
    pattern = re.compile(rf"\b{re.escape(name)}\s*\(", re.IGNORECASE)
    for match in pattern.finditer(masked, start, end):
        opening = masked.find("(", match.start(), end)
        closing = closing_paren(masked, opening)
        if closing is not None and closing <= end: return match.start(), closing
    return None

def force_nf(simulate):
    masked = mask_comments_and_quotes(simulate)
    method = re.compile(
        r"""\bmethod\s*=>\s*(?:"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|[A-Za-z_]\w*)""",
        re.IGNORECASE,
    )
    match = method.search(masked)
    if match:
        return simulate[:match.start()] + 'method=>"nf"' + simulate[match.end():]

    opening, closing = masked.find("("), masked.rfind(")")
    if opening < 0 or closing < opening: return simulate
    inside = masked[opening + 1:closing].strip()
    if not inside: return simulate[:opening + 1] + '{method=>"nf"}' + simulate[closing:]

    brace = masked.find("{", opening, closing)
    if brace < 0: return simulate
    separator = "" if not masked[brace + 1:closing].strip() else ", "
    return simulate[:brace + 1] + 'method=>"nf"' + separator + simulate[brace + 1:]

def get_simulate(text, model, actions):
    regions = [(actions[2], actions[3])] if actions else []
    regions.append((model[1], len(text)))
    for start, end in regions:
        call = find_call(text, "simulate", start, end)
        if call: return text[call[0]:call[1]]
    return None

def action_comments(text, actions):
    if not actions: return []
    comments = []
    for line in text[actions[2]:actions[3]].splitlines(keepends=True):
        _, comment, _ = split_comment(line)
        if comment: comments.append(comment)
    return comments

def fix_actions(text, changes, warnings):
    model = find_block(text, "model")
    if not model: raise ConversionError("Could not find a complete 'model' block.")
    actions = find_block(text, "actions")
    simulate = get_simulate(text, model, actions)
    comments = action_comments(text, actions)

    if actions and model[0] <= actions[0] < model[3]:
        text = text[:actions[0]] + text[actions[1]:]
        model = find_block(text, "model")

    lines = ["begin actions"]
    lines.extend("    " + comment for comment in comments)
    lines.append("    writeXML()")
    if simulate:
        simulate = force_nf(simulate.strip())
        lines.extend("    " + line.strip() for line in simulate.splitlines())
        changes.append('Kept simulate(...) and forced method=>"nf".')
    else:
        warnings.append("No simulate(...) action was found.")
    lines.append("end actions")

    before = text[:model[3]].rstrip()
    end_model = text[model[3]:model[1]].lstrip("\r\n")
    changes.append("Removed other actions and inserted writeXML().")
    return before + "\n\n" + "\n".join(lines) + "\n" + end_model

def convert_file(input_file, force=False):
    source = Path(input_file).expanduser().resolve()
    if not source.is_file(): raise ConversionError(f"File not found: {source}")
    if source.suffix.lower() != ".bngl": raise ConversionError("Input file must end in .bngl.")
    if source.stem.endswith("_molclustpy"): raise ConversionError("File already appears converted.")

    output = source.with_name(f"{source.stem}_molclustpy.bngl")
    if output.exists() and not force:
        raise ConversionError(f"Output exists: {output.name}. Use --force to replace it.")

    result = ConversionResult(output)
    text = source.read_text(encoding="utf-8")
    text = replace_empty_sites(text, result.changes)
    text = fix_populations(text, result.changes, result.warnings)
    text = fix_actions(text, result.changes, result.warnings)

    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text(text.rstrip() + "\n", encoding="utf-8")
        temporary.replace(output)
    finally:
        if temporary.exists(): temporary.unlink()
    return result
