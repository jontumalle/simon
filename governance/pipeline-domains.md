# Pipeline Domains — Intake, Decision Engine, and Outcome

Simon splits product work into three contract-bounded domains. This lets teammates and agents work in parallel without stepping on each other.

```mermaid
flowchart LR
    D1["1. Intake (Scouting)\nDiscover leads · Verify media\nDigest audio/video · Enrich metadata"]
    C1(["Canonical Contracts\nmvp_contracts.json\ntalent_profile_schema.json"])
    D2["2. Decision Engine\nCalibrated triage · Blind critics\nPreserve disagreement & star math"]
    C2(["Shortlist & Assessment\npending_human_review"])
    D3["3. Outcome (Evolving / TBD)\nPaid showcase offer · Scouting Studio\nFuture roster / booking actions"]

    D1 --> C1 --> D2 --> C2 --> D3
    D3 -. "Targeted EnrichmentTask\n(Second-Take / Missing Proof)" .-> D1
```

---

## Domain Ownership & Boundaries

| Domain | Core Job | Repo Paths | Branch Prefix |
| :--- | :--- | :--- | :--- |
| **1. Intake (Discovery & Investigation)** | **Stage 1:** Discover unranked leads (`discovery-scout` on `gemini-4-hydrogen`). **Stage 2:** Build factual artist dossiers via 4 Managed Agents (`identity-resolver`, `footprint-profiler`, `signal-forensics`, `track-record-mapper` on `gemini-4-argon`). | `simon/investigator*.py`, `simon/discovery_ui.py`, `agents/discovery-scout/`, `agents/identity-resolver/`, `agents/footprint-profiler/`, `agents/signal-forensics/`, `agents/track-record-mapper/` | `intake/<slug>` |
| **2. Decision Engine (Screening & Taste)** | **Stage 3:** Run parallel Advocate vs. Skeptic debate (`screen-advocate`, `screen-skeptic` on `gemini-4-carbon`), rubric verdict (`screening-judge` on `gemini-4-neon`), and HITL DSPy + `gemini-decision-1` calibration. | `simon/screening.py`, `simon/screening_ui.py`, `simon/taste_profile_ui.py`, `agents/screen-advocate/`, `agents/screen-skeptic/`, `agents/screening-judge/` | `decision/<slug>` |
| **3. Outcome (Production & Studio)** | **Stage 4:** Turn approved `ScreeningPacket` + Stage 2 Dossier into human-gated callback drafts (`showcase-producer` on `gemini-4-carbon`) across the unified 4-Stage Studio UI. | `simon/web.py`, `simon/phases.py`, `simon/demo_flow.py`, `agents/showcase-producer/` | `outcome/<slug>` |

---

## Cross-Domain Contract Rules

1. **Contracts First**: If you need a new field between domains, update [mvp_contracts.json](../data/mvp_contracts.json) or [talent_profile_schema.json](../data/talent_profile_schema.json) on a branch first.
2. **Epistemic Blinding**: Intake never leaks social vanity metrics into vocal-craft evaluation inputs.
3. **Traceable Evidence**: Every Decision Engine claim and Outcome recommendation must retain playable `source_url` and `MM:SS` timestamps from Intake.
4. **Outcome Modularity**: Keep Decision Engine outputs decoupled from single-event assumptions so we can swap or expand Outcome mechanics cleanly as we define them.
