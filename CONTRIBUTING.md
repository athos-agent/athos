# Contributing

Thanks for wanting to improve Athos. Everything you contribute is released under the Apache License 2.0, the same as
the rest of the project. To share a way of working for the gallery instead of code, see
[gallery/CONTRIBUTING.md](gallery/CONTRIBUTING.md).

## Sign off every commit

We use the [Developer Certificate of Origin 1.1](https://developercertificate.org/): each commit from an outside
contributor carries a line stating that you wrote the change, or otherwise have the right to submit it:

```
Signed-off-by: Ada Lovelace <ada@example.com>
```

Commit with `git commit -s` and git writes that line from your name and email. A pull request with any commit that
lacks it cannot be merged.

## From idea to pull request

1. For anything beyond a small fix, open an issue first so we can agree on the approach.
2. Fork the repository and make your change on a branch of its own.
3. Keep each commit to one capability, and put its tests in the same commit.
4. Before opening the pull request, run the tests and let the gitleaks pre-commit hook pass:
   - Python: `HOME=$(mktemp -d) python3 -m unittest discover -s tests -t .` (a throwaway home, so your own `~/.athos`
     is never touched)
   - the Claude Code hooks module: `claude plugin test .`

## Keep the user's data on their machine

Athos sends nothing off a person's machine unless they explicitly ask. Telemetry, remote logging and new network
calls need an issue and a discussion before any code.
