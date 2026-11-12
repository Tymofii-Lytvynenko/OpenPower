# Property tests

Run `python -m pytest tests/property -q --hypothesis-profile=fast` locally.
Use `--hypothesis-profile=ci` for regular verification, or
`--hypothesis-profile=extended --hypothesis-show-statistics` for deeper runs.
The profiles set maximum examples to 25, 100, and 500, and state-machine steps
 to 10, 30, and 60 respectively. Finite domains can be exhausted earlier.
Hypothesis stores local examples in `.hypothesis/`; reproduce a failure with
its reported seed or example. Add a deterministic regression test for a fixed bug.

These tests use small independent states and test doubles; they do not yet cover
full save/load migrations or the full geopolitical simulation.
