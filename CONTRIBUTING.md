# Contributing to mdgoat

Thanks for helping keep the AI input layer clean. 🐐

mdgoat is intentionally small and dependency-free. Contributions that keep it
that way — especially **new detectors** — are the most welcome kind.

## Development setup

```bash
git clone https://github.com/shahcolate/mdgoat
cd mdgoat
pip install -e .
python -m unittest discover -s tests -v
```

No dependencies to install beyond the package itself. The test suite is pure
`unittest` and runs in well under a second.

## Ground rules

- **Zero runtime dependencies.** Standard library only. If a feature seems to
  need a dependency, open an issue first — there is usually a stdlib way.
- **Deterministic.** No network calls, no LLM calls, no randomness. Same input
  must always produce the same output.
- **The cleaner never changes meaning.** `mdgoat clean` may only apply fixes
  that are provably content-preserving (removing invisible smuggling channels,
  reversing byte-exact mojibake, normalizing whitespace). Anything that
  requires judgement is a *scanner* finding, reported but never auto-applied.
- **mdgoat must pass its own gate.** `mdgoat scan README.md --fail-on high`
  runs in CI. Keep example payloads out of prose, or express them so they do
  not themselves trip a rule.

## Adding a detector

1. Pick the right module in `mdgoat/detectors/` (`security`, `artifacts`,
   `structure`, or `efficiency`).
2. Write a function `detect_<thing>(doc: Document) -> Iterable[Finding]` and add
   it to that module's `DETECTORS` list.
3. Give it a fresh rule ID in the module's series (`SEC0xx`, `ART0xx`, …) and
   register it in `mdgoat/rules.py` so `mdgoat rules` documents it.
4. If it has a safe, deterministic fix, wire it into `mdgoat/cleaner.py` and set
   `fixable=True`.
5. Add tests covering both a true positive **and** a clean input that must not
   fire (false-positive guard). We care a lot about false positives.
6. Any non-ASCII literals in `mdgoat/` source must be written as `\uXXXX`
   escapes — the package eats its own dog food.

## Submitting

- Keep PRs focused. One detector or one fix per PR is ideal.
- Make sure `python -m unittest discover -s tests` is green.
- Describe the real-world case your change addresses.

## Reporting security-relevant gaps

If you know of a smuggling or injection technique mdgoat misses, that is a
feature request, not a vulnerability in mdgoat itself — open a normal issue
using the "New detector" template. See [SECURITY.md](SECURITY.md) for how to
report an actual vulnerability in the tool.

## Releasing (maintainers)

mdgoat publishes to PyPI via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC — no
stored tokens), driven by `.github/workflows/publish.yml`.

One-time setup: on PyPI add a trusted publisher (or a *pending* publisher for
the first release) with owner `shahcolate`, repo `mdgoat`, workflow
`publish.yml`, environment `pypi`; then create a GitHub environment named
`pypi` under **Settings → Environments**.

Each release:

1. Bump the version in **both** `pyproject.toml` and `mdgoat/__init__.py`, and
   move the `[Unreleased]` notes in `CHANGELOG.md` under the new version.
2. Merge that to `main`.
3. **Draft a new GitHub Release** for tag `vX.Y.Z` (Releases → Draft a new
   release → create the tag on publish). Publishing the Release creates the tag
   *and* triggers `publish.yml`, which builds the sdist + wheel, runs
   `twine check`, and uploads to PyPI.
4. Verify: `pip install --upgrade mdgoat && mdgoat --version`.

A failed publish can be re-run from the **Actions** tab (the workflow also
accepts a manual `workflow_dispatch`). PyPI will not accept re-uploading an
existing version, so always bump first.
