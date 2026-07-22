import shutil, subprocess, tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
SITE_NAME, TIMEOUT = "site", 120

class ConversionError(Exception): pass
class ConversionResult:
    def __init__(self, output_file):
        self.output_file = output_file
        self.changes, self.warnings = [], []
        self.validation_passed, self.validation_message = None, ""

def strip_comment(line):
    p = line.find("#")
    return (line, "") if p < 0 else (line[:p], line[p:])

def mask_comments(text):
    out, quote, escaped, comment = list(text), None, False, False
    for i, c in enumerate(text):
        if comment:
            if c in "\r\n": comment = False
            else: out[i] = " "
        elif quote:
            if c not in "\r\n": out[i] = " "
            if escaped: escaped = False
            elif c == "\\": escaped = True
            elif c == quote: quote = None
        elif c == "#": comment = True; out[i] = " "
        elif c in "'\"": quote = c; out[i] = " "
    return "".join(out)
def find_block(text, name):
    op, cl = f"begin {name.lower()}", f"end {name.lower()}"
    start, body = None, None
    pos = 0
    for line in text.splitlines(keepends=True):
        end = pos + len(line)
        cc = " ".join(strip_comment(line)[0].strip().lower().split())
        if start is None and (cc == op or cc.startswith(op + " ")):
            start, body = pos, end
        elif start is not None and (cc == cl or cc.startswith(cl + " ")):
            return start, end, body, pos
        pos = end
    return None

def find_empty_calls(text):
    calls, p = [], 0
    while p < len(text):
        if not (text[p].isalpha() or text[p] == "_") or (p > 0 and (text[p-1].isalnum() or text[p-1] == "_")):
            p += 1; continue
        end = p + 1
        while end < len(text) and (text[end].isalnum() or text[end] == "_"): end += 1
        op = end
        while op < len(text) and text[op].isspace(): op += 1
        cl = op + 1
        if op < len(text) and text[op] == "(":
            while cl < len(text) and text[cl].isspace(): cl += 1
            if cl < len(text) and text[cl] == ")":
                calls.append((p, cl + 1, text[p:end])); p = cl + 1; continue
        p = end
    return calls

def replace_empty_sites(text, changes):
    b = find_block(text, "molecule types")
    if not b: raise ConversionError("Missing 'molecule types'.")
    names = {name for line in text[b[2]:b[3]].splitlines() for _, _, name in find_empty_calls(strip_comment(line)[0])}
    for name in names:
        rep, total = f"{name}({SITE_NAME})", 0
        for bn in ("molecule types", "seed species", "observables", "reaction rules"):
            tgt = find_block(text, bn)
            if not tgt: continue
            lines = []
            for line in text[tgt[2]:tgt[3]].splitlines(keepends=True):
                code, comm = strip_comment(line)
                pieces, last = [], 0
                for start, end, found in find_empty_calls(code):
                    if found == name:
                        pieces.extend([code[last:start], rep]); last = end; total += 1
                code = "".join(pieces) + code[last:] if last > 0 else code
                lines.append(code + comm)
            text = text[:tgt[2]] + "".join(lines) + text[tgt[3]:]
        if total: changes.append(f"Changed {name}() to {rep} in {total} place(s).")
    return text

def fix_populations(text, changes, warnings):
    seed = find_block(text, "seed species")
    if not seed: raise ConversionError("Missing 'seed species'.")
    base, errs, lines, names = text.count("\n", 0, seed[2]) + 1, [], [], set()
    for offset, line in enumerate(text[seed[2]:seed[3]].splitlines(keepends=True)):
        code, comm = strip_comment(line)
        toks = code.split()
        if len(toks) >= 2:
            val = toks[-1]
            try:
                num = Decimal(val)
                if not (num.is_finite() and num >= 0 and num == num.to_integral_value()):
                    errs.append(f"Invalid count line {base+offset}: '{val}'")
                else:
                    fixed = str(int(num))
                    if fixed != val:
                        p = code.rfind(val)
                        code = code[:p] + fixed + code[p + len(val):]
                        changes.append(f"Changed seed count {val} to {fixed}.")
            except InvalidOperation:
                if val and (val[0].isalpha() or val[0] == "_") and all(c.isalnum() or c == "_" for c in val):
                    names.add(val)
                else: warnings.append(f"Line {base+offset}: unverified '{val}'.")
        lines.append(code + comm)
    text = text[:seed[2]] + "".join(lines) + text[seed[3]:]
    if names:
        params = find_block(text, "parameters")
        if not params: raise ConversionError("Missing 'parameters'.")
        p_base, p_lines, found = text.count("\n", 0, params[2]) + 1, [], set()
        for offset, line in enumerate(text[params[2]:params[3]].splitlines(keepends=True)):
            code, comm = strip_comment(line)
            toks = code.split()
            if toks and toks[0] in names and len(toks) >= 2:
                name, val = toks[0], (toks[2] if len(toks) > 2 and toks[1] == '=' else toks[1])
                found.add(name)
                try:
                    num = Decimal(val)
                    if not (num.is_finite() and num >= 0 and num == num.to_integral_value()):
                        errs.append(f"Invalid param count line {p_base+offset}: '{val}'")
                    else:
                        fixed = str(int(num))
                        if fixed != val:
                            p = code.rfind(val)
                            code = code[:p] + fixed + code[p + len(val):]
                            changes.append(f"Changed param {name} to {fixed}.")
                except InvalidOperation: warnings.append(f"Param '{name}' not numeric.")
            p_lines.append(code + comm)
        text = text[:params[2]] + "".join(p_lines) + text[params[3]:]
        for m in (names - found): warnings.append(f"Seed ref '{m}' not found.")
    if errs: raise ConversionError("Population validation failed:\n" + "\n".join(errs))
    return text

def get_closing_paren(text, start):
    depth, quote, escaped = 0, None, False
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if escaped: escaped = False
            elif c == "\\": escaped = True
            elif c == quote: quote = None
        elif c in "'\"": quote = c
        elif c == "(": depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0: return i + 1
    return None
def force_nf_method(sim_call):
    lowered, start = mask_comments(sim_call).lower(), 0
    while True:
        pos = lowered.find("method", start)
        if pos < 0: break
        if (pos == 0 or not (lowered[pos-1].isalnum() or lowered[pos-1] == "_")) and \
           (pos + 6 >= len(lowered) or not (lowered[pos+6].isalnum() or lowered[pos+6] == "_")):
            arrow = pos + 6
            while arrow < len(sim_call) and sim_call[arrow].isspace(): arrow += 1
            if sim_call[arrow:arrow+2] == "=>":
                val_start = arrow + 2
                while val_start < len(sim_call) and sim_call[val_start].isspace(): val_start += 1
                end = val_start
                if end < len(sim_call) and sim_call[end] in "'\"":
                    q = sim_call[end]; end += 1; esc = False
                    while end < len(sim_call):
                        c = sim_call[end]; end += 1
                        if esc: esc = False
                        elif c == "\\": esc = True
                        elif c == q: break
                else:
                    while end < len(sim_call) and (sim_call[end].isalnum() or sim_call[end] == "_"): end += 1
                return sim_call[:pos] + 'method=>"nf"' + sim_call[end:]
        start = pos + 6
    brace = sim_call.find("{")
    return sim_call if brace < 0 else sim_call[:brace+1] + 'method=>"nf", ' + sim_call[brace+1:]

def find_ident_call(text, name, start_pos=0):
    p = start_pos
    while p < len(text):
        idx = text.lower().find(name, p)
        if idx < 0: return -1
        if (idx == 0 or not (text[idx-1].isalnum() or text[idx-1] == "_")) and \
           (idx + len(name) >= len(text) or not (text[idx+len(name)].isalnum() or text[idx+len(name)] == "_")):
            paren = idx + len(name)
            while paren < len(text) and text[paren].isspace(): paren += 1
            if paren < len(text) and text[paren] == "(": return idx
        p = idx + 1
    return -1

def fix_actions(text, changes, warnings):
    masked = mask_comments(text)
    actions = find_block(text, "actions")
    model = find_block(text, "model")
    if not model: raise ConversionError("Could not find a complete model block.")
    end_model = model[3]

    sim_call = None
    search_start = actions[2] if actions else end_model
    sim_start = find_ident_call(masked, "simulate", search_start)
    if sim_start >= 0 and (not actions or sim_start < actions[3]):
        paren = masked.find("(", sim_start)
        if paren >= 0:
            close = get_closing_paren(masked, paren)
            if close: sim_call = text[sim_start:close]

    new_code = force_nf_method(sim_call).strip() if sim_call else ""
    if not sim_call: warnings.append("No simulate(...) action found.")
    changes.append("Inserted writeXML() and NFsim method before end model.")
    new_actions = f"\nbegin actions\n    writeXML()\n    {new_code}\nend actions\n"

    if actions:
        text = text[:actions[0]] + text[actions[1]:]
        masked = mask_comments(text)
        model = find_block(text, "model")
        end_model = model[3]

    line_start, line_end = model[3], model[1]
    clean_lines, p = [], line_end

    while p < len(text):
        next_nl = text.find("\n", p)
        if next_nl < 0: next_nl = len(text)
        line_str, masked_line = text[p:next_nl], masked[p:next_nl]
        code = masked_line.strip()
        standalone = False

        if code:
            i = 0
            while i < len(code) and (code[i].isalnum() or code[i] == "_"): i += 1
            if i:
                opening = i
                while opening < len(code) and code[opening].isspace(): opening += 1
                standalone = opening < len(code) and code[opening] == "("

        if not standalone:
            clean_lines.append(line_str + "\n" if next_nl < len(text) else line_str)
        else:
            paren = masked.find("(", p)
            close = get_closing_paren(masked, paren) if paren >= 0 else None
            if close:
                p = close
                while p < len(text) and text[p] in " \t": p += 1
                if p < len(text) and text[p] == ";": p += 1
                while p < len(text) and text[p] in " \t": p += 1
                if text.startswith("\r\n", p): p += 2
                elif p < len(text) and text[p] in "\r\n": p += 1
                continue

        p = next_nl + 1 if next_nl < len(text) else len(text)

    return text[:line_start] + new_actions + text[line_start:line_end] + "".join(clean_lines)
def validate_bngl(filepath, validator=None):
    if validator:
        val_path = Path(validator)
        cmd = ["perl", str(val_path)] if val_path.suffix.lower() == ".pl" else [str(validator)]
    else:
        bng2, bionetgen = shutil.which("BNG2.pl"), shutil.which("bionetgen")
        if bng2: cmd = ["perl", bng2]
        elif bionetgen: cmd = [bionetgen, "run", "-i"]
        else: return None, "BioNetGen not found in PATH."

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / filepath.name
        shutil.copy2(filepath, tmp_file)
        try:
            res = subprocess.run([*cmd, str(tmp_file)], cwd=tmp_dir, text=True, capture_output=True, timeout=TIMEOUT, check=False)
        except Exception as e: return False, f"Failed validator: {e}"

    out, err = res.stdout.strip(), res.stderr.strip()
    msg = "\n\n".join(filter(None, [f"STDOUT:\n{out}" if out else "", f"STDERR:\n{err}" if err else ""]))
    if res.returncode != 0: return False, msg or "Validation failed."
    for line in (out + "\n" + err).splitlines():
        cl = line.strip().lower()
        if cl.startswith(("error", "fatal", "syntax error")):
            return False, msg or "Validation failed."
    return True, msg or "Validation passed."

def convert_file(input_file, run_validation=True, validator=None, force=False):
    src = Path(input_file).expanduser().resolve()
    if not src.is_file(): raise ConversionError(f"File not found: {src}")
    if src.suffix.lower() != ".bngl": raise ConversionError("Input must end in .bngl")
    if src.stem.endswith("_molclustpy"): raise ConversionError("Already converted file.")
    out = src.with_name(f"{src.stem}_molclustpy.bngl")
    if out.exists() and not force: raise ConversionError(f"Output exists: {out.name}. Use --force.")

    res = ConversionResult(out)
    text = src.read_text()
    text = replace_empty_sites(text, res.changes)
    text = fix_populations(text, res.changes, res.warnings)
    text = fix_actions(text, res.changes, res.warnings)

    tmp = out.with_name(f".{out.name}.tmp")
    try:
        tmp.write_text(text.rstrip() + "\n"); tmp.replace(out)
    finally:
        if tmp.exists(): tmp.unlink()

    if run_validation:
        res.validation_passed, res.validation_message = validate_bngl(out, validator)
    return res
