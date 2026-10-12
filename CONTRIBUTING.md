# Contributing

Welcome! Bug reports, translations, documentation and code improvements are appreciated.

1. Fork the repo and create a focused branch.
2. Use Python 3.11 and install core/dev requirements; keep optional models outside Git.
3. Add regression tests for changed behavior. Preserve existing projects/settings,
   atomic saves, consent defaults and cancellation. Do not silently migrate user data.
4. Check VI/EN/ZH UI labels. Never translate user cue text, filenames or API keys.
5. Run Python/Node tests and describe exactly what was verified (mock vs real model/GPU).
6. Open a pull request explaining the change and its limitations.

By contributing, you agree that your contribution may be distributed under the
repository MIT license. Do not submit third-party code/assets without compatible
licensing and notices; the project's MIT does not relicense external models/assets.

Please strip secrets and personal media from logs/screenshots. For suspected security
issues, do not post exploit details or real credentials publicly; contact the maintainer
through an available private channel before disclosure. No production support SLA.
