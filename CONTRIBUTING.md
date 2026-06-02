# Contributing to Yoink

Thanks for your interest! Yoink is a personal, **non-commercial** project
(licensed under **CC BY-NC-SA 4.0**). Contributions are welcome in that spirit.

## How to propose a change

Every change goes through one of these — please don't expect direct write access:

1. **Open an issue first** for anything non-trivial. Use the **bug report** or
   **feature request** template. This is the place to *ask* for a change or
   report a problem, and it lets us agree on the approach before you spend time
   on code.
2. **Fork the repo and open a pull request** for the actual code. Keep PRs
   focused and link the issue they address; the pull-request template lists the
   checks to run. Maintainer review + merge is how changes land on `main`.

By contributing, you agree that your contribution is licensed under the
project's **CC BY-NC-SA 4.0** terms (non-commercial, share-alike, with
attribution) — the same terms that protect the rest of the project.

## Ground rules

- **Commits** in English, with a subject **and** a body explaining the *why*.
- Keep the JSON contract in sync: `backend/app/models/media.py` (Pydantic) and
  `src/types/download.ts` (TypeScript) mirror each other 1:1.
- Run the checks before opening a PR:
  - Frontend: `npm run build`, `npm run lint`, and `npm run test:e2e` if the UI
    changed.
  - Backend: `pytest` (from `backend/`).
  - Keep `npm audit` at **0 vulnerabilities**.
- Match the surrounding style — the backend is strictly typed.

## Reporting security issues

Do **not** open a public issue for vulnerabilities. Use GitHub's private
Security Advisories:
<https://github.com/ayozetr/yoink-app/security/advisories/new>.

See [`CLAUDE.md`](CLAUDE.md) for the architecture and per-layer commands, and
[`docs/`](docs/) for the deeper guides.
