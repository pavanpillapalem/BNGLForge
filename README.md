# BNGLForge

BNGLForge helps automate the preperation of a '.bngl' model for use with MolClustPy.

## What the code does

The converter:

- Reads one '.bngl' model.
- Keeps the original file unchanged.
- Creates a new file named '<model>_molclustpy.bngl'.
- Adds 'writeXML()'.
- Removes actions that are not needed by MolClustPy.
- Changes the simulation method to 'nf'.
- Changes molecules declared with no sites, such as 'A()', to 'A(site)' throughout the model.
- Preserves all numeric values exactly as written.
- Optionally validates the converted model with BioNetGen.
- Renames failed validation output to '<model>_molclustpy_FAILED_VALIDATION.bngl'.

## Requirements

- Python 3.10 or newer
- BioNetGen and 'BNG2.pl' for optional validation

## Running BNGLForge

Replace `<model_name>` with the name of your BNGL file.

### macOS/Linux

```bash
python3 run.py <model_name>.bngl
```

### Windows

```powershell
py run.py <model_name>.bngl
```

This creates:

```text
<model_name>_molclustpy.bngl
```

### Options

Skip validation:

```bash
python3 run.py <model_name>.bngl --skip-validation
```

Specify `BNG2.pl`:

```bash
python3 run.py <model_name>.bngl --validator /path/to/BNG2.pl
```

Overwrite an existing output:

```bash
python3 run.py <model_name>.bngl --force
```
