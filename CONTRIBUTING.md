# Contributing to xcaf-pmi

Contributions are welcome: bug reports, fixes, features and documentation.

Before review, run what CI runs:

```sh
python -m pip install -e '.[test]'
XCAF_PMI_REQUIRE_FIXTURES=1 python -m pytest -q tests
```

## Developer Certificate of Origin

Contributions are accepted under the project's licence, Apache-2.0 (its section 5 covers
contributions). Each commit must be signed off to certify the
[Developer Certificate of Origin 1.1](https://developercertificate.org/): that you wrote the
change, or otherwise have the right to submit it under that licence. Sign off with
`git commit -s`, which adds a line with your real name and email:

```
Signed-off-by: Your Name <you@example.com>
```

A check on pull requests from forks confirms every commit is signed off. To sign off commits
already made, `git rebase --signoff main` and force-push the branch.
