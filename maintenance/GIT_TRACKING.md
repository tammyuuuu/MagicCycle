# Git tracking boundaries

The repository distributes website source, the complete `docs/` site, research
engines and tests, raw/clean research inputs, versioned `workspace_data/`, and
the research results consumed by packaging, tests and independent replay.
The existing offline-export test also needs the deliberately retained CSV/JSON
and research-source HTML snapshots in `data_cache/`.

Local screenshots, logs, ZIP recovery archives, browser downloads, duplicate
HTML previews and the old V1/V2 `out_*` folders are not distributed. They remain
on the original computer. Rebuild old analysis outputs with their corresponding
study scripts; rebuild previews with `workspace_ui_20261022/build_previews.py`.
The `*_signals.csv` outputs are reproducible through each research directory's
`reaccept.py`; current packaging and independent replay do not read them.

Do not ignore every directory named `results` or `data_cache`: several nested
directories contain required data. `.gitattributes` preserves the original
bytes of hash-audited research and archive inputs across Windows checkouts.

Run `python run_tests.py --browser` to check the shipped content. Historical
recovery-file tests check local ZIPs/screenshots when available and explicitly
skip those optional artifacts in a fresh clone; required non-image data remains
mandatory. On the original computer these artifacts are still fully checked.

The local-only audit and recovery bundle for the tracking cleanup are in
`maintenance/git_push_cleanup_local/`. They are intentionally excluded from Git.
No website or research computation is changed by these tracking rules.
