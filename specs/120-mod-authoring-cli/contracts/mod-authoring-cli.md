# Contract: Mod Authoring CLI

## Commands

```text
openpower mod create <mod-id> [--name NAME] [--depends ID ...] [--project-root PATH]
openpower mod validate <mod-id> [--project-root PATH]
```

The default dependency for `mod create` is `base`. Module IDs and dependency IDs must
begin with a lowercase letter and contain only lowercase letters, digits, and
underscores.

## Create behavior

- Resolve the target as `<project-root>/modules/<mod-id>`.
- Create the standard starter files only if the target does not exist.
- Return a clear creation message and the validation command after success.
- Fail rather than overwrite an existing target.

## Validate behavior

- Resolve the module from the selected project's `modules/` directory.
- Compose and initialize the module through the runtime and execute one headless tick.
- On success, report load order, systems, schemas, initialized tables, and handled actions.
- On failure, return a command error and do not report the module as valid.
