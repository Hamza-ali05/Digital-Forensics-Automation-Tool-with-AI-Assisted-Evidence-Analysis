# Git Workflow

## Main Branch

- `main` is always deployable.
- All merges to `main` require a pull request.

## Feature Branches

Naming pattern:

```text
feature/DFAT-{number}-{short-description}
```

Example: `feature/DFAT-001-project-scaffold`.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `docs:`
- `chore:`

## Pull Requests

Each PR must:

1. Pass all tests (`make test`).
2. Pass linting and type checks (`make lint`, `make type-check`).
3. Describe the change purpose and linked DFAT ticket/number where applicable.
