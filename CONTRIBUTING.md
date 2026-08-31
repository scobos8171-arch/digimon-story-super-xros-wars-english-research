# Contributing

Thank you for helping translate and understand Super Xros Wars.

## Before opening a pull request

- Work from a clean branch.
- Never commit `.nds`, `.dst`, `.dsv`, BIOS, firmware, emulator binaries, or
  bulk-extracted game archives.
- Remove personal absolute paths from scripts and reports.
- Preserve native dimensions, indexed-color constraints, transparency, and
  archive allocation rules when editing graphics.
- Include a before/after screenshot or decoded QA image for visual changes.
- Include containment evidence showing which ROM files/entries changed.
- Confirm ARM9, overlays, and unrelated entries remain unchanged when expected.

## Reporting untranslated content

Include:

1. screenshot;
2. exact menu/story/battle location;
3. steps to reproduce;
4. Japanese text and proposed natural English;
5. whether it appears dynamic, sprite-based, background-based, or unknown;
6. game build/hash used.

Save states can contain copyrighted/runtime data. Keep them off the repository;
share hashes and coordinate privately with maintainers when a state is needed.

## Reverse-engineering submissions

Document the input, method, and observed output. Label hypotheses clearly. A
useful finding should be reproducible by someone who did not perform the first
analysis.

Preferred evidence table fields:

`system`, `file`, `entry`, `offset/address`, `size`, `encoding/format`,
`runtime context`, `evidence`, `confidence`, `researcher`, `date`.

## Translation style

- Prefer natural English over rigid word-for-word translation.
- Preserve established Digimon terminology and character names.
- Keep text within the native UI space.
- Do not invent specificity that is absent from the Japanese.
- Flag uncertain readings for review.

## Pull-request checklist

- [ ] No copyrighted ROM data is included.
- [ ] New behavior is documented.
- [ ] Relevant tests or QA artifacts pass.
- [ ] Changed archives/entries are listed.
- [ ] Output hashes are recorded when producing a build.

