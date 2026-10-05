# Force-field parameter set comparison

Reusable tooling to compare **physical properties** from isolated BLAST `main1.py` run folders (lattice, cohesive energy, elastic constants). Internal objectives (`finalObj`, `*.obj`) stay out of the main CSV.

## Layout

| Path | Role |
|------|------|
| `blast_lib/property_comparison/` | Library: build CSVs, plots, validate |
| `examples/*.json` | Workspace config (potentials, elastic constants) |

## Config (`comparison.json`)

```json
{
  "workspace": "/path/to/property_comparison_3sets",
  "comparison_subdir": "comparison",
  "elastic_constants": ["C11", "C22", "C12", "C66"],
  "potentials": [
    { "run_dir": "set_A", "label": "Set A", "per_set_csv": "set_A_target_vs_predicted.csv" },
    { "run_dir": "published_ML_Tersoff", "label": "Published ML-Tersoff", "fixed_m": "1.0",
      "parameter_vector": ["1.53800", "..."] }
  ]
}
```

- **workspace**: parent of per-potential run directories (each with `reports/ho.report`).
- **potentials**: any number of named sets; excluded potentials are omitted from the config (not hard-coded A/B/C).
- **elastic_constants**: subset of elastic headers to compare (default C11, C22, C12, C66).

## Commands

From repo root (`PYTHONPATH` = repo root):

```bash
python -m blast_lib.property_comparison regenerate --config scripts/property_comparison/examples/tersoff_4pot_comparison.json
```

Subcommands: `build`, `plot`, `validate`, `regenerate`.

Outputs under `{workspace}/comparison/`:

- `property_comparison.csv`, `parameter_comparison.csv`
- Per-set `*_target_vs_predicted.csv`
- `elastic_plot_source.csv`, `elastic_errors_source.csv`
- `barplot_*.png` (lattice, cohesive, elastic)

Phonon PNGs and slide decks are **not** produced by this module; keep them as separate workspace artifacts.

## Perlmutter example

Copy `examples/tersoff_4pot_comparison.json` into the comparison workspace and point `workspace` at `test_runs/property_comparison_3sets`. Regenerate CSVs/plots without re-running LAMMPS.

## Tests

```bash
pytest tests/test_property_comparison.py -q
```
