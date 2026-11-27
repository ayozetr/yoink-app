<!--
Thanks for contributing to Yoink! Keep the subject of your commits in English
with a body explaining the why (see AGENTS.md → Git conventions).
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

- [ ] `cargo fmt` + `cargo clippy --release -- -D warnings` pass (CI gates on both)
- [ ] `cargo test` passes (in `desktop/` and/or `backend-rs/`, whichever changed)
- [ ] `cargo build --release` succeeds

## Contract sync

<!-- If you touched the JSON contract, both sides must match. -->

- [ ] Not applicable
- [ ] the backend Rust structs (`backend-rs/src/`) and the desktop client (`desktop/src/api.rs`) were updated together

## Notes for the reviewer

<!-- Screenshots for UI changes, trade-offs, follow-ups. Optional. -->
