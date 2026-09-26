# Sample data

Anonymised Costplan-style tender workbook for automated tests and Stage B demos.

| File | Purpose |
|------|---------|
| `DEMO_Tender_Comparison_Workbook.xlsx` | Fictional project / client / contractors (happy path) |
| `DEMO_Failing_Workbook.xlsx` | Incomplete workbook for validation / FAILED path |
| `build_sample_workbook.py` | Regenerates the happy-path workbook |
| `build_failing_workbook.py` | Regenerates the failing workbook |

```powershell
python sample_data/build_sample_workbook.py
python sample_data/build_failing_workbook.py
```

Template shape mirrored in the sample:

- `SUMMARY` — first Rate/Total pair is **Costplan**, then each tenderer
- **Variance from Costplan** (workbook label; also accepts **Variance to Budget**) =
  Final Adjusted tender sum − Costplan budget; staged as `VarianceToBudget`
- Level 3 sheets — Costplan + all contractor Qty/Unit/Rate/Total blocks (ingestion still stages the selected contractor)

Tracked via `.gitignore` exception `!sample_data/*.xlsx` (global `*.xlsx` remains ignored elsewhere).
