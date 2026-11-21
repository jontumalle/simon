# Process Observation & Continuous System Improvement (`pm/process/`)

This directory holds Simon's **meta-operational memory** — observed workflow signals, skill invocations, hook behaviors, parallel-window interactions, and calibrated system evolution proposals.

It is maintained via the [process-observer](../../.agents/skills/process-observer/SKILL.md) skill and consumed/evolved by a **dedicated System Improver agent**.

---

## Design Charter: Non-Binary System Improvement

1. **No Binary Pass/Fail or On/Off Framing**:
   - Workflows, hooks, and skills are **never** classified as simply "working vs. broken" or reduced to binary "keep vs. delete" choices.
   - Instead, every mechanism is mapped across its **operating spectrum**: *where and why it creates velocity*, *under what boundary conditions it creates drag*, and *a graduated spectrum of refinements* with explicit tradeoffs.
2. **Empirical First (`inspect_sessions.py`)**:
   - Ground observations in real session transcripts via `python3 .agents/skills/process-observer/scripts/inspect_sessions.py` rather than anecdotes alone.
3. **Preserve Tailwinds While Smoothing Drag**:
   - Explicitly log what is **working well** (`velocity-tailwind`) alongside frictions so iterative system tuning never degrades high-performing workflows.

---

## Files in This Folder

| File | Role |
| :--- | :--- |
| **[observations.md](./observations.md)** | Chronological, append-only empirical log of observed session signals (skill reads, hook blocks, permission friction, parallel-window races, toolchain quirks, and velocity wins) |
| **[synthesis.md](./synthesis.md)** | Living analytical synthesis for the System Improver agent: what works, root-cause dynamics of active friction, and calibrated non-binary adaptation spectrums |
