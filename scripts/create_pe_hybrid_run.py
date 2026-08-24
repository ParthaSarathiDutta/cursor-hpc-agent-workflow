#!/usr/bin/env python3
"""Create ML-Tersoff-1_PE_hybrid folder only (no BLAST / objective runs)."""

import shutil
from pathlib import Path

BASE = Path("/global/cfs/cdirs/m4597/partha/AgenticBLAST")
SRC = BASE / "ML-Tersoff-1_PE"
DST = BASE / "ML-Tersoff-1_PE_hybrid"


def patch_main1(text: str) -> str:
    old_block = """    polymorphs_energy_order = sorted([
        Path(fname).name for fname in
        glob.glob(GEO.path+'/*.data')
    ], key=lambda s:int(s.split('/')[-1].split('.')[0]))
    

    polymorphs_energy_order=list(polymorphs_energy_order[i] for i in [0])
    
    print(polymorphs_energy_order)"""

    new_block = """    all_polymorphs = sorted([
        Path(fname).name for fname in
        glob.glob(GEO.path+'/*.data')
    ], key=lambda s:int(s.split('/')[-1].split('.')[0]))

    # Hybrid strategy (PE_hybrid): one structure for lattice/eos/phonon/elastic;
    # both polymorphs for cohesive-energy ordering (PE_12 ce logic).
    polymorphs_single = list(all_polymorphs[i] for i in [0])
    polymorphs_ce = list(all_polymorphs[i] for i in [0, 1])

    print("polymorphs_single:", polymorphs_single)
    print("polymorphs_ce:", polymorphs_ce)"""

    if old_block not in text:
        raise SystemExit("main1.py expected block not found")

    text = text.replace(old_block, new_block)
    text = text.replace("polymorphs_energy_order", "polymorphs_single")
    text = text.replace(
        "    w_stage = np.ones(len(polymorphs_single)) # +1 for ordering\n"
        "    group = blast.data.load('geo').group()\n"
        "    for structure in polymorphs_single:",
        "    w_stage = np.ones(len(polymorphs_ce)) # +1 for ordering\n"
        "    group = blast.data.load('geo').group()\n"
        "    for structure in polymorphs_ce:",
        1,
    )
    text = text.replace(
        "return HO.finalobj(f\"{param_str} {structure.split('.')[0]}/"
        "{polymorphs_single[-1].split('.')[0]} {prop} maxAE% > 3%\")",
        "return HO.finalobj(f\"{param_str} {structure.split('.')[0]}/"
        "{polymorphs_ce[-1].split('.')[0]} {prop} maxAE% > 3%\")",
        1,
    )
    return text


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)

    shutil.copytree(
        SRC,
        DST,
        ignore=shutil.ignore_patterns(
            "blast.log",
            "analytics.dat",
            "mctree.restart",
            "treestructure.nh",
            ".ipynb_checkpoints",
            "__pycache__",
            "*.png",
            "phonon_p.txt",
            "phonon_t.txt",
            "phonon_p.yaml",
            "Cv_p.txt",
            "total_dos.dat",
            "current.data",
            ".model.json.swp",
            ".settings.json.swp",
            "old_tmp_symlink.txt",
            "tmp",
        ),
    )

    reports = DST / "reports"
    if reports.exists():
        shutil.rmtree(reports)
    reports.mkdir()

    (DST / "main1.py").write_text(patch_main1((DST / "main1.py").read_text()))

    (DST / "STRATEGY.md").write_text(
        """# ML-Tersoff-1_PE_hybrid

Hybrid fitting strategy derived from comparing ML-Tersoff-1_PE and ML-Tersoff-1_PE_12.

## Objective split (main1.py)
- **polymorphs_single [0]**: lattice, EOS, phonon, elastic (same as PE)
- **polymorphs_ce [0, 1]**: cohesive energy + polymorph ordering (same as PE_12)

## Before running
- Seed model.json / mcts_restart from best PE trial if desired
- Submit search via RunBOP.py or your usual workflow
"""
    )

    paths = sorted(BASE.glob("ML-Tersoff*"))
    (BASE / "input.txt").write_text("".join(f"{p}/\n" for p in paths))

    print(f"Created {DST}")


if __name__ == "__main__":
    main()
