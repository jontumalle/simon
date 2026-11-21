# 2026-11-21 · Lead Generation & Generalist Investigator Alignment

Distilled from Kevin & JT's Wispr Flow sync (`2:19–2:30 PM EST`, [Wispr Flow notes](https://notes.wisprflow.ai/shared/Lz9kFMMLDxKVP4MaQo4LXtRr4hwtW5kvX8Yb-qkAypk)). Raw transcript is kept locally in gitignored `local/transcripts/2026-11-21-1419-pipeline-and-two-layer-design.md`.

*(Note: Follow-up 2:34–2:36 PM EST recording — "Scout Investigator Tool Development", [Wispr Flow link](https://notes.wisprflow.ai/shared/F8Uqn7ogLLcwKRjrQJUUBsRVf5TJYc7c4_2BKxJxN4I) — currently reports `has_transcript: false` in Wispr Flow.)*

---

## Aligned Pipeline Diagram

```mermaid
flowchart LR
    Input["Search Brief + Count (N)"] --> S1["Stage 1: Lead Generation (Discovery)\nFind N people + log useful sources"]
    S1 -->|"Unranked list of people"| S2{"Stage 2: Investigator / Profiler Fleet\n(Generalist solo actors, 1 per person)"}
    S2 --> I1["Investigator A\n(Person 1)"]
    S2 --> I2["Investigator B\n(Person 2)"]
    S2 --> I3["Investigator C\n(Person N)"]
    I1 & I2 & I3 --> Out["Output Now:\nPeople + Objective Factual Data\n(No ranking yet)"]
    Out -. "Later (Deferred)" .-> S3["Stage 3: Outcome / Rules Engine\n(Filter, sign/pass, re-run on new releases)"]

    subgraph Layers["Two-Layer Agent Design"]
        L1["Layer 1: General Process (AGENTS.md)\nDomain-agnostic: discover -> investigate -> log sources"]
        L2["Layer 2: Domain Skills (.agents/skills/music/)\nMusic-specific: where to look, multimodal audio/video"]
        L1 --- L2
    end
```

---

## Key Decisions Confirmed
1. **Build Stages 1 and 2 First:** Ship **Lead Generation (Discovery)** and **Lead Processing (Investigator / Profiler)** first; defer Stage 3 (**Outcome / Rules Engine**) until real candidate data accumulates.
2. **Output Contract Right Now:** Return a configurable list of people (`N`) with **objective, factual data** — **no ranking or scoring yet**.
3. **Generalist Investigators Over Premature Source Specialists:** Assign each found person to one solo generalist Investigator that gathers everything about them. Only spin out source-specific specialists later once execution traces show where agents spend the most time.
4. **Shared Source Discovery Log:** Document strong sources discovered during runs so other agents reuse them.
5. **Two-Layer Design (Domain-Agnostic Process + Music Skills):**
   - **Layer 1 (`AGENTS.md`):** General, objective discovery and investigation process (transferable to any vertical such as real estate).
   - **Layer 2 (`.agents/skills/music/`):** Music-only skills right now so we exercise multimodal audio and video understanding.
