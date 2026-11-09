# Smoke-test record

Command executed successfully:

```bash
python run_omega_interactions.py --smoke --seed-start 10000 --workers 2 --output /tmp/smoke_omega_parallel
```

Observed validation summary:

- Actual small planner executions: **8 / 8**
- Logical rows produced: **12 / 12**
- One task hash per `(Map A, task_count, seed)` group: **passed**
- Look-ahead congestion enabled on Map A: **passed**
- All three omega-interaction study builders exercised: **passed**

This smoke test uses a reduced 5-task instance and a reduced grid. It validates the engineering pipeline only; it is not formal experimental evidence. The formal evidence is separately recorded in `results_omega_interactions/omega_interactions_completion_status.json` and uses 330 complete one-shot CPS-A executions.
