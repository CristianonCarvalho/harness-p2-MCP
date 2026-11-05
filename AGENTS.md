# Agent Directives

## Project context

- **Stack:** Python 3.13, uv, hatchling, pytest. Pacote `taxlaw` em `src/`.
- **Test command:** `uv run pytest`
- **Conventions:** identificadores em inglês; comentários, mensagens e notas em português; comentários didáticos explicam o porquê. Testes offline, sem `conftest.py`, independentes do diretório atual. Só dados públicos ou sintéticos: nunca CPF/CNPJ válido escrito no repositório.

## Task execution

- Follow the scope and target files specified in the assigned task.
- Preserve pre-existing changes and avoid changes outside the scope.
- Run relevant tests and clearly report results and limitations. Do NOT run the entire test suite: MeisterRouter's gate runs it afterward.

## Writing a plan for MeisterRouter

If you are asked to write a plan (not to implement a subtask), use the native flow:

```bash
meister plan guide
meister plan new -o plan.md
meister plan import plan.md -o plan.json
meister plan validate plan.json
```

Read the rules with `plan guide`, fill in the tasks in the skeleton, then convert and validate
it; the architect runs the validated plan. If you use the `superpowers:writing-plans` skill,
the format is the same (accepted by `plan import`).

## If you are a MeisterRouter worker

Consider yourself a worker if `MEISTER_WORKER=1` (or, in older installations, `MEISTER_IN_PANE=1`) is set in the environment or if you
are in a worktree created for a subtask. Implement the assigned task directly,
only in the target files. Run relevant tests and report the evidence. Do NOT run the
entire test suite: MeisterRouter's gate runs it afterward.
Do not run MeisterRouter classification, worker execution, orchestration, or control
commands; do not delegate the task to another agent.
