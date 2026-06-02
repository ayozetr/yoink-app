<!--
Thanks for contributing to Yoink! Keep the subject of your commits in English
with a body explaining the why (see CLAUDE.md → Git conventions).
-->

## What this changes

<!-- One or two sentences on the change and the problem it solves. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / internal
- [ ] Docs only
- [ ] Build / packaging / CI

## How it was tested

<!-- Tick what you ran; the contract spans both sides, so keep them in sync. -->

- [ ] `npm run build` (type-check + build) passes
- [ ] `npm run lint` passes
- [ ] `npm run test:e2e` passes (if UI behavior changed)
- [ ] `pytest` passes (if the backend changed)
- [ ] `npm audit` is still at 0 vulnerabilities

## Contract sync

<!-- If you touched the JSON contract, both sides must match. -->

- [ ] Not applicable
- [ ] `backend/app/models/media.py` and `src/types/download.ts` were updated together

## Notes for the reviewer

<!-- Screenshots for UI changes, trade-offs, follow-ups. Optional. -->
