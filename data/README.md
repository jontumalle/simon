# Data & Fixtures Guide (`data/`, `examples/`, `local/`)

Simon separates data into three clear locations so private artist info and large media never leak into git:

| Directory | Tracked in Git? | What Belongs Here |
| :--- | :---: | :--- |
| **`data/`** | Yes | JSON schemas (e.g., manifest & agent report schemas), rubric definitions, anonymized evaluation benchmarks |
| **`examples/`** | Yes | Small, fictional or explicitly public sample fixtures (`examples/showcase.json`) used by `python3 -m simon` |
| **`local/`** | **No** (`.gitignore`) | Real artist submissions, `.mp3`/`.wav` audio files, artist contact details, raw meeting transcripts (`local/transcript.md`), and live run outputs |
