How the lab analyses a small study so that anyone gets the same result from the same files, in this order. Each stage
goes in `analysis.json` under `stages` (the names below) once it is done.

1. `raw`: keep the raw file read-only (never edit or overwrite `data.csv`) and record its name and its SHA-256
   checksum in `raw`.
2. `cleaning`: exclude only what the registered protocol rule says, written as code, before looking at any result.
   Never drop a value for being extreme or an "outlier": a rule decided after seeing the data bends the result. List
   the excluded participant ids in `exclusions`.
3. `sample`: count n per group after the exclusions.
4. `test`: with fewer than 30 in any group, a t-test's assumptions can't be checked: use a non-parametric test. Two
   independent groups → `Mann-Whitney U` (report U for group A: the rank sum of A minus nA(nA+1)/2, ranks over both
   groups together, ties get the average rank). Use only the Python standard library.
5. `effect`: report the matching effect size, the rank-biserial correlation, `2*U/(nA*nB) - 1`, named
   `rank-biserial`.
6. `medians`: report medians and quartiles per group, not means: quartiles with
   `statistics.quantiles(x, n=4, method="inclusive")`, `iqr` as [q1, q3].
7. `report`: the script, the Python version and the random seed (write `seed`, even if nothing is random) go with the
   results; RESULTS.md says why a non-parametric test was used (n per group, under 30).
8. `results_written`: write `analysis.json` with `stages` and every field of the request, and RESULTS.md.
