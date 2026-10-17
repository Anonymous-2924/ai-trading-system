# Daily trading logs

One CSV and one Markdown file per team member, appended once per pipeline run
and **committed back to this repository** by the `trading-analysis` workflow,
so a 15-20 day history accumulates instead of evaporating with the runner.

```
student_1.csv  student_1.md
student_2.csv  student_2.md
student_3.csv  student_3.md
```

They appear on the first run. See the README section "Per-member daily logs"
for the column list and the two guarantees (a run that cannot read the account
still appends a row; a logging failure never breaks a trading run).
