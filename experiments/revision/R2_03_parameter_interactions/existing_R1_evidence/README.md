# Existing Reviewer-1 Gaussian evidence (reused, not rerun)

The enclosed files are copied from `result_R1_gaussian_sensitivity.zip`.
The original `config.json` records:

- task counts: A = 50,70; B = 250,280; C = 150,200;
- look-ahead in h: A = true; B/C = false;
- seeds: 42,43,44,45,46;
- Gaussian baseline: L=T=1, sigma_l=sigma_t=2;
- one-factor sweeps: L,T in {0,1,2,3}; sigma_l,sigma_t in {0.5,1,2,4}.

R2-03 does not merge these five old seeds with the new R2-03 seeds.
