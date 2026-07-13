<!-- Thanks for contributing to mdgoat! Keep PRs focused — one detector or fix each. -->

## What this changes

<!-- A short description of the change and the real-world case it addresses. -->

## Type of change

- [ ] New detector / rule
- [ ] New auto-fix in the cleaner
- [ ] Bug fix
- [ ] Docs / tooling
- [ ] Other:

## Checklist

- [ ] `python -m unittest discover -s tests` is green
- [ ] Added tests, including a **false-positive guard** (clean input that must not fire) for any new detector
- [ ] No new runtime dependencies
- [ ] The cleaner (if touched) is still content-preserving and idempotent
- [ ] Any non-ASCII literals in `mdgoat/` are written as `\uXXXX` escapes
- [ ] `mdgoat rules` updated (`mdgoat/rules.py`) if a rule was added
