---
id: run-a-reproducible-analysis
title: Run a reproducible analysis
when: analysing experimental or survey data so that someone else gets the same result from the same files
profession: science
lang: en
---

## #raw
**When:** the data arrives.
**Do:** keep the raw files read-only and record their names, checksums and where they came from.
**Links:** [[run-a-reproducible-analysis#cleaning]]

## #cleaning
**When:** before looking at any result.
**Do:** write each cleaning rule as code (exclusions, outliers, missing values), each with its reason.
**Because:** rules decided after seeing the results bend them.
**Links:** [[run-a-reproducible-analysis#sample]]

## #sample
**When:** the data is clean.
**Do:** count n per group and check the assumptions of the planned test (normality, equal variances).
**If:** n < 30 in any group, or the assumptions fail → [[choose-a-non-parametric-test]]
**Because:** with small samples a t-test's assumptions can't be checked and its p-value misleads.
**Links:** [[run-a-reproducible-analysis#report]]

## #report
**When:** the test has run.
**Do:** report effect sizes with confidence intervals, not only p-values; the script, the package versions and the random seed go with the results.
**Because:** a result nobody can rerun is an anecdote.
