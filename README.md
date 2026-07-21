# BNGLForge

BNGLForge prepares `.bngl` models for MolClustPy.

## Files

* `converter.py`: conversion code
* `run.py`: converts one BNGL file
* `metadata_compatibility.py`: checks metadata before converting

## Requirements

* Python 3.10 or newer
* BioNetGen and `BNG2.pl` for validation

## Convert one model

### macOS/Linux

```bash
python3 run.py <model>.bngl
```

### Windows

```powershell
py run.py <model>.bngl
```

The original file is kept. The output is:

```text
<model>_molclustpy.bngl
```

The converter:

* Adds `writeXML()`
* Changes the simulation method to `nf`
* Removes unnecessary actions
* Changes empty molecules such as `A()` to `A(site)`
* Preserves numeric values
* Can validate the output with BioNetGen

### Options

Skip validation:

```bash
python3 run.py <model>.bngl --skip-validation
```

Specify `BNG2.pl`:

```bash
python3 run.py <model>.bngl --validator /path/to/BNG2.pl
```

Overwrite an existing output:

```bash
python3 run.py <model>.bngl --force
```

## Convert using metadata

The folder must contain `metadata.yaml` and one `.bngl` file.

Check MolClustPy compatibility:

```bash
python3 metadata_compatibility.py <folder> -molclustpy
```

Check NFsim compatibility:

```bash
python3 metadata_compatibility.py <folder> -nfsim
```

The script converts the model only when the selected compatibility value is `true`.

### RuleHub example

```bash
python3 scripts/metadata_compatibility.py \
Published/Mitra2019/04-egfrnf -nfsim
```
