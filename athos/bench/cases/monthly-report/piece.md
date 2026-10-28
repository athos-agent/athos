1. Source: `data/orders-YYYY-MM.csv` (order_id, date, region, amount_cents, status).
2. Count only orders with status `paid`. Leave out every order whose id starts with `TEST-`: those are QA orders.
3. Amounts are in cents. Report dollars with two decimals.
4. One row per region, sorted by revenue, highest first. Region names as they appear in the file.
5. Write `reports/YYYY-MM.md`: the title `# Sales report — <Month> <YYYY>` (e.g. `# Sales report — October 2026`),
   then a table `| Region | Orders | Revenue (USD) |`, then a last row `| Total | <orders> | <revenue> |`.
6. Also write `reports/YYYY-MM.json`: `{"regions": {"<region>": {"orders": <n>, "revenue": <dollars>}}, "total":
   {"orders": <n>, "revenue": <dollars>}}`, revenue as a number with two decimals.
