# Source provenance

All scientific inputs come from23 supplied sources. No external dataset, repository or web material is incorporated. Manuscript TRC-26-01887 identifies the project and five authors; Response's unrelated legacy template identifier is not propagated.

Exact archives remain unchanged, including corrupt archive19. Portable edits have source/public SHA256 and redacted diffs. Numerical extractions are unchanged; derived outputs are explicitly separate.

Canonical choices:20 original code/results;04–07 separate R1 results plus21 code/plots;09 R2.02 data;08 R2.03 data;13–18 R2.04 results/jobs/snapshot/workloads/attempts/code;10 final R2.05 replaced results plus11 code;12 R2.07 code plus19 merged results;23 R2 plots.

R2.04's28 executed snapshot files match delivered code. Seven original baseline core files in each of R2.04/05/07 match current experiment.zip (21 comparisons). Historical manifests can reference differently packaged original ZIPs; a container SHA difference is not assumed to mean planner changes.

Raw execution hashes, historical local paths and quality records are preserved. Public manifest rebasing does not change historical run identity. Old diagnostics, smoke/pilot artifacts, caches and duplicate results remain in source archives but are not counted as final outcomes.

All PDFs remain staging-only with identity/hash recorded. The exact original ZIP contains a supplied credential and stays private; portable copies use an environment variable and diffs redact its value. No license, DOI, publication or upload to GitHub occurred.

## Final update source identities

New archives are named `provenance/source_archives/R2-02.zip` and `R2-03.zip` to avoid collisions with historical numeric prefixes. Latest upload numbering is recorded in `provenance/update_sources_20261102.json`. Numeric prefixes in the existing inventory refer to the previous source list, not the latest upload order. R2.04 consolidated uploads were not reprocessed. The R2.07 reupload is identical and retained under its prior canonical archive path; there is no duplicate numerical dataset.

R2.02/R2.03 code, including supplied vendor modules and compat.py, is kept byte-identical and runs in an isolated subprocess from its own directory. These standalone namespaces are deliberately preserved, not rewritten into the older public package imports. The omega data also remain inside the unchanged source tree for provenance; the canonical analysis copy is results/revision/R2_03_parameter_interactions/omega and is counted once.
