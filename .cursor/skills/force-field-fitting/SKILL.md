---
name: force-field-fitting
description: >-
  BLAST Tersoff force-field fitting on NERSC — run directories, main1.py
  objective, ho.report analysis, polymorph strategies, and Perlmutter workflow.
  Use when working on force-field fitting, BLAST, Tersoff potentials, LAMMPS
  fitting runs, AgenticBLAST, main1.py, RunBOP.py, ho.report, or model.json.
---

# Force-field fitting (BLAST)

## Read first

- Living notes: [`skills/Force Field Fitting.General.md`](../../skills/Force%20Field%20Fitting.General.md)
- Full framework: [`constitution/General framework for Tersoff force field fitting using BLAST.md`](../../constitution/General%20framework%20for%20Tersoff%20force%20field%20fitting%20using%20BLAST.md)
- HPC: [`.cursor/rules/perlmutter-blast.mdc`](../../rules/perlmutter-blast.mdc)

## Workflow

1. Read `settings.json` and `model.json` in the run directory before diagnosing.
2. Trace the objective in `main1.py` (property ladder, polymorph selection, early exit).
3. Use `reports/ho.report` for trial outcomes; `blast.log` for LAMMPS/runtime errors.
4. Prefer material-agnostic placeholders — no hardcoded element names or CFS paths in shared code.
5. Heavy LAMMPS/search on compute nodes via Slurm; login node for edit/submit only.

## Mandatory — auto-update notes (do not ask permission)

Before **completing any task** where you learned or confirmed something reusable about BLAST force-field fitting:

1. Open [`skills/Force Field Fitting.General.md`](../../skills/Force%20Field%20Fitting.General.md).
2. If the fact is not already there, add a **short bullet** under the best section.
3. Skip one-off trial counts, material-specific paths, and unverified guesses.
4. For large architectural findings, update `constitution/` and add a one-line pointer in the General notes file.

This step is automatic — the user should not need to prompt you to update the file.

## Analysis helpers

- [`scripts/analysis_ho_report.py`](../../scripts/analysis_ho_report.py)
- [`scripts/analysis.ipynb`](../../scripts/analysis.ipynb)
