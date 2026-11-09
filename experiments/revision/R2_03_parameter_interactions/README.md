# R2.03 — supplied experiment source, joint/cross and omega evidence

Added from R2-03.zip. Executable files are unchanged. Original design/commands are in SOURCE_README.md and R2_03_omega_interactions/README.md. Run these standalone modules from their own directory in fresh processes so their local config/vendor names cannot collide.

Saved numerical sources: 2,130 joint/cross logical rows from results_R2_03.zip, plus 390 omega logical rows and 330 unique runs from the added code ZIP. The canonical omega data are results/revision/R2_03_parameter_interactions/omega. Their duplicate inside this source tree is unchanged provenance and is not counted again. All ten Map-A/load/seed task hashes match the original joint/cross data.

From repository root, replot without running experiments:

```bash
python scripts/replot.py R2_03
python scripts/replot.py R2_03_omega
```

The supplied source's historical run counts describe the author's saved experiments. No simulation was run in this update. See REPRODUCIBILITY.md for explicitly separated future simulation commands.
