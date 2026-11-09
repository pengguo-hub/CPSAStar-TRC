# Cleanup changelog

126 source-derived files differ in the portable tree. Both SHA256 values and redacted diffs are in provenance/portable_changes.csv and provenance/diffs. Exact original archives remain unchanged. Every expanded numerical result remains byte-identical.

Changes:
- Explicit repository package imports replace sibling/SRTP-parent imports. Vendor directory renamed portable_vendor.
- sys.path mutations removed; worker subprocesses use python -m from repository root.
- Personal machine I/O paths become repository-relative. Missing inputs are documented, not substituted.
- Two literal credentials removed from executable original-paper source; environment lookup replaces them. Exact original remains private; diffs redact values.
- Public verifier manifests rebased with new paths/hashes and supplied hashes retained. Raw historical execution hashes stay unchanged.
- R1 plotting paths rebased; original one-shot plot skips absent algorithm series instead of failing. No invented outcomes.
- Added safe validators, indexing/statistical/replot wrappers, labeled R2.02 SD reconstruction and R2.07 core-CSV wrapper.
- Historical old/smoke/pilot data remain compressed in original archives, separate from canonical outcomes. Caches excluded.
- Source maps, reproducibility instructions, citation skeleton and reports added. No license, DOI, experiment parameter or seed invented.

Planner search/reservation/field/ticket/priority/rollback function ASTs are unchanged across74 files and812 definitions, excluding import statements. The damaged R2.07 source archive is preserved exactly, not silently repaired.

## 2026-11-02 final update

Added unchanged R2.02/R2.03 code, including the R2.02 statistics dependency and the omega result package. Registered saved-data-only replot commands and isolated imports. Kept R2.04 unchanged. Rechecked R2.07 and recorded unchanged bytes/read failures. Rebuilt indexes, source maps, outer archives and hashes. New wrappers only copy/read saved data and call supplied statistics/plotting; no planner functions were changed, and no experiment main was executed in this update.
