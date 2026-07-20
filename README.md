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

## How to run it

Run the converter from the repository folder:

python3 run.py path/to/model.bngl

Example:

python3 run.py models/example.bngl


This creates:

models/example_molclustpy.bngl

## Command options

Skip BioNetGen validation:

python3 run.py model.bngl --skip-validation

Provide the path to `BNG2.pl`:

python3 run.py model.bngl --validator /path/to/BNG2.pl

Replace an existing converted file:

python3 run.py model.bngl --force

Options can be combined:

python3 run.py model.bngl --validator /path/to/BNG2.pl --force
