#!/usr/bin/env python3
"""Fail if Bayesian training sources or private raw artifacts enter the project."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN=("bayes_opt.py","process_ckpt.py","generate_bin_config.py","generate_vars.py","config_bayes.yaml","dummy_prob.bin")
found=[p for p in ROOT.rglob("*") if p.is_file() and p.name in FORBIDDEN]
if found:
    raise SystemExit("FORBIDDEN_BAYES_FILES\n"+"\n".join(str(p) for p in found))
print("EXCLUSION_CHECK=PASS")
