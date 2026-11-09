# R2.02 — supplied experiment source and saved-result analysis

Added from R2-02.zip. All supplied executable files are unchanged. See SOURCE_README.md for the original design and preparation protocol. Run source entry points from this directory in a fresh Python process; compat.py establishes the original vendor namespace. Do not import multiple standalone experiment packages into one Python process.

To reanalyze saved results, from the repository root:

```bash
python scripts/replot.py R2_02_CI
python plotting/revision/R2/R2_2/reconstruction/reconstruct_response_sd.py
```

The first command uses the supplied bootstrap-CI conventions on a temporary raw-data copy and writes derived tables separately; the second is the earlier explicitly labeled SD reconstruction. No simulations are executed. The supplied CI plot has fixed axis limits; the SD reconstruction uses automatic limits. Neither is described as an exact rendering of both conventions.

Formal simulation, only if intentionally requested later, uses `python run_representation_experiment.py --seeds 5 --seed-start 42 --suite primary --references reference_artifacts --output ../../../../outputs/R2_02_new` from this directory. Prepare formal historical/learned reference artifacts as described in SOURCE_README first; reference_smoke is not a formal reference set. Those simulations were not run for this delivery.

Source digest in the added code is 508482deb82803acbbf2b176b603923da4ee02d4112eb0b65268a8e4941f1300; the saved execution manifest records 6659acdcb9520766a94f5100c9da861ccfbedf5b77cada1a1d46a2eabbef3a9a. These differ. This delivery preserves both and does not claim the supplied package is an identical historical checkout.
