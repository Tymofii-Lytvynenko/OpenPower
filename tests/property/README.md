# Property tests

Run `python -m pytest tests/property -q --hypothesis-profile=fast` locally.
Use `--hypothesis-profile=ci` for regular verification, or
`--hypothesis-profile=extended --hypothesis-show-statistics` for deeper runs.
Profiles set maximum examples to 25, 100, and 500 and state-machine steps to
10, 30, and 60. Finite domains can be exhausted earlier.

Filesystem and full-world tests are marked `slow` and excluded by default.
Run them separately with `python -m pytest tests/property -q -m slow
--hypothesis-profile=ci`. These integration tests have smaller example limits.
They use temporary directories, and the headless runner reads project data only.

Hypothesis stores local examples in `.hypothesis/`; reproduce a failure with
its reported seed or example. Add a deterministic regression test for a fixed bug.
