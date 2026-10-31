---
id: analyse-an-experiment-reproducibly
title: Analyse an experiment's data so another lab can repeat it
when: analysing the data of an experiment or a measurement campaign (lab results, sequencing, sensors, materials tests) for a paper, a report or a decision, so the same analysis can be run again on other data
---

## #raw_stays_raw
**When:** before touching the data.
**Do:** copy the raw files to a folder the analysis never writes to, and record their names, sizes and checksums. All the work happens in a script, never by hand in a spreadsheet.
**Because:** a result that cannot be traced back to untouched raw data cannot be reproduced.
**Links:** [[analyse-an-experiment-reproducibly#cleaning_rules]]

## #cleaning_rules
**When:** cleaning the data.
**Do:** apply MY rules, written down before looking at the results. Examples to replace with your own: drop runs whose control failed; flag as outliers points more than 3 median absolute deviations away, and report them, never delete them silently; the instrument's detection limit is the floor.
**Because:** the small cleaning decisions papers leave out are where reproducibility is lost; deciding them after seeing the result is how bias creeps in.
**Links:** [[analyse-an-experiment-reproducibly#analysis]]

## #analysis
**When:** the data is clean.
**Do:** compute with code the planned analysis, with every parameter in one place at the top of the script (seed, thresholds, versions of the libraries). Show effect sizes with their intervals, not only p-values.
**Because:** arithmetic is done with code; a parameter hidden in a cell is a parameter nobody can repeat.
**Links:** [[analyse-an-experiment-reproducibly#check]]

## #check
**When:** the results are out.
**Do:** run the whole script again from the raw copy in a clean folder and confirm the numbers are identical. List what was excluded and why.
**Links:** [[analyse-an-experiment-reproducibly#package]]

## #package
**When:** the analysis is final.
**Do:** leave together the script, the parameters, the list of exclusions and this way of working, so another lab can run the same method on their own data. What the results mean, and what to claim, is the person's call.
**Because:** a method that travels with the paper is a protocol others can use, not a story they must trust.
