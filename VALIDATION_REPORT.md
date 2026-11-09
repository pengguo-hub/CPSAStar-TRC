# Validation report

| Check | Result / evidence |
|---|---|
|Source inventory|25 distinct source files accounted for (previous23 plus2 added code ZIPs); R2.07 reupload reconfirmed|
|Source ZIP reads|All intact except249 files in archive19; archive_integrity.json|
|R2.07 directory entry|One additional damaged logs/ header; total250 invalid entries|
|RAR|260 file members read with system libarchive|
|R1 duplicates|Byte/member/numerical equality as appropriate; R1_duplicate_comparison.json|
|Planner function AST|91 files,995 definitions unchanged after excluding imports|
|Executed R2.04 snapshot|28/28 byte-identical|
|Original baseline identity|21/21 byte-identical comparisons|
|R2.04 selected payloads|105/105 agree on8 checked metrics|
|R2.07 run payloads|237 agree with CSV;3 unreadable; all240 rows retained|
|Portable checks|Compile passed;20/20 imports;3/3 source verifiers; no prohibited executable path/import/credential candidates|
|Reported values|183/183 match at reported precision|
|Plotting|Eleven revision plotting jobs and additional reconstructions passed; generated-file QA recorded|
|Final delivery|Outer ZIP CRC and fresh-extraction hash/import/compile checks recorded in delivery_validation.json|

These checks do not establish complete end-to-end replication. Historical verifier wording about unchanged files refers to its supplied manifest; portable hashes differ after import/path edits, with original hashes retained separately.

The three damaged run IDs are RING_N120_backlog_46_S1_L0_P1_R1, RING_N120_backlog_46_S1_L1_P1_R1, RING_N120_backlog_46_S1_L1_P1_R0. Other damaged files are84 checkpoints and162 logs. One logs/ directory header is also corrupt. Exact damaged bytes are preserved; no silent archive repair or row removal occurred.

R2.04 has180 final CSV rows but106 attempt directories and105 selected payloads. Crosschecks cover completed,throughput,waiting_time,flow_time,queue_length,planning_seconds,rollbacks,arrived. Event-level coverage is incomplete.

Generated PDFs were rendered and PNGs decoded. Principal revision/reconstruction figures were visually inspected. Incomplete intermediate image files were regenerated or rasterized from their valid regenerated PDFs; final file QA is explicit. Font fallback prevents pixel-identity claims.

## Earlier verification incident

An earlier interrupted validation loop passed --help to a legacy R1 Gaussian runner that does not parse options, unintentionally entering its experiment main. The environment later reset; completion and transient outputs cannot be established. None of those outputs is used or included. All delivered numerical evidence comes from the prior sources plus the added R2.03 omega evidence. The safe validation script never invokes runner mains.

R2.02/R2.03 runners, the R2.02 statistics module and omega data have now been supplied. Original inputs/seed outcomes, complete request-level payloads, exact historical R2.02 source identity, historical environment and publication decisions remain unresolved. See docs/AUTHOR_DECISIONS.md.

## 2026-11-02 final update

- 20/20 isolated module imports and 3/3 source verifiers passed; Python compilation passed. New code retains its supplied standalone namespace and vendor compatibility shim; this explicitly scoped exception is exercised in fresh processes.
- 801 extracted files from the two added code ZIPs match their source members byte for byte. Source and data archives pass the documented checks except the already identified R2.07 inner-member failures.
- R2.02 CI plotting and data checks passed. run_validation.csv is derived from stored run JSON validation records; no new collision simulation was executed. Original numerical inputs are unchanged.
- Omega: 390 logical rows, 330 unique JSON records; 3,960 numeric JSON/CSV checks; 468 summary mean/SD rows; 10 paired task blocks match the earlier R2.03 data.
- R2.02 supplied-source digest 508482deb82803acbbf2b176b603923da4ee02d4112eb0b65268a8e4941f1300 differs from stored execution digest 6659acdcb9520766a94f5100c9da861ccfbedf5b77cada1a1d46a2eabbef3a9a. Neither value is overwritten or treated as equivalent.
- R2.07 reupload SHA-256 a621cd6dd453d60c5d6af5dc684500ef104e417181950ed8d7179d0329c0f6f3 equals the previous archive. The full recheck still identifies 250 unreadable entries (249 files plus one directory). Its 240 CSV rows remain usable.
- Outer ZIP integrity, fresh extraction and hashes are recorded in CPS-Astar-delivery-validation.json delivered beside the ZIPs. They do not imply the nested R2.07 archive is intact.
