# Contract: Headless Simulation CLI

## Commands

```text
openpower sim run [simulation options]
openpower sim compare [simulation options] [--runs N]
```

Shared options are `--project-root`, `--mods`, `--years`, `--days`, `--seed`, `--player`,
`--save`, `--actions`, `--output`, `--run-id`, `--snapshot-interval`,
`--diagnostics-interval`, `--no-export-tables`, and `--fail-on-diagnostics`.
`sim compare` additionally accepts `--runs`.

## Result contract

- `sim run` prints a run ID, state fingerprint, and report path.
- A failed run prints each recorded failure and returns status 1.
- Invalid arguments or runtime exceptions print an error to standard error and return
  status 2.
- `sim compare` prints whether fingerprints matched and the comparison report path; it
  returns status 0 on a match and status 1 on a mismatch.
- Artifact paths are rooted in the selected output directory or the default
  `user_data/simulations/<run-id>` directory.

## Determinism contract

Runs that are compared use the same run configuration, including modules, seed, player,
save, duration, and action script. Comparison is based on persistent-state fingerprints.
