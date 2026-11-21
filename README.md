# Simon

Simon is a live showcase producer that discovers overlooked singers and pays them to perform. First Listen NYC is the proposed pilot. A local sponsor pays Simon to produce the showcase, artists receive a guaranteed fee, and Simon earns the remaining margin after production costs. Once the format has an audience, ticket revenue can help finance later shows.

> We find the singer you would have missed, then put them on a paid stage.

## Gemini 4 NYC Hackathon

The public organizer brief invites ambitious Gemini 4 projects across advanced reasoning, visual coding, robotics, and world models. The [official event listing](https://events.cerebralvalley.ai/e/gemini-4-nyc) also lists $5,000 for Best Use of Managed Agents and $2,500 in Shop Cash for Best Use of Shopify. The public materials provide broad themes and prize categories. A separate set of mandatory problem statements could not be verified publicly.

## Run the Taste-Brief Vocal Scout MVP

Simon's Taste-Brief MVP takes a natural-language taste brief, discovers public YouTube performances via a **Gemini Managed Agent** (`simon-discovery-scout`) + zero-signup `YouTubeConnector`, evaluates clips directly in **Gemini 4 Hydrogen** for timestamped musical choices (`phrasing`, `dynamics`, `interpretation`, `arrangement`) and recording context (`live` / `studio` / `unclear`), triggers a second-take lookup when evidence is thin, stores normalized records in SQLite (`local/simon.db`), and synthesizes a **<= 3 singer Listening Shortlist** via `simon-synthesis-scout`.

### 1. Interactive Web Studio (Recommended Demo)

```sh
python3 -m simon serve --port 8765
```

Open `http://127.0.0.1:8765` to enter a taste brief, inspect the **Managed Agent & Evaluator Trace**, and click **Play First (@ MM:SS)** to jump straight to the exact musical moment Simon described. Works immediately with verified public YouTube clips in demo mode, and switches to live Gemini 4 + Managed Agent calls automatically when `GEMINI_API_KEY` is set in `.env` or your shell.

### 2. CLI Taste-Brief Scout

```sh
# Verified public YouTube demo run (persists records to local/simon.db)
python3 -m simon scout --brief "Find singers who reinterpret familiar songs through phrasing or arrangement."

# Full live run (Managed Agent discovery + public YouTube search/oEmbed + Gemini 4 Hydrogen video input + Managed Agent synthesis)
export GEMINI_API_KEY="your-api-key"
python3 -m simon scout --live --brief "Stripped-back soul with distinctive phrasing"
```

*(Platform note: Gemini supports public YouTube URLs directly as video inputs, whereas SoundCloud's API terms prohibit feeding API-accessed tracks into AI models.)*

---

## Run the *First Listen NYC* Showcase Starter

From the repository root with Python 3.9 or later:

```sh
python3 -m simon
```

This prints the fictional showcase run, the two independent assessments, a producer recommendation, and an unsent callback draft with an illustrative $250 artist guarantee.

For actual Gemini calls, set `GEMINI_API_KEY` in your shell environment. Copy `examples/showcase.json` into the ignored `local/` directory and replace the fictional auditions with opt-in submissions and a real event brief. Each audition has an `id`, `artist`, `consent`, `artist_notes`, and either `performance_notes` or an optional `audio` path. Audio paths are relative to the manifest. The starter accepts MP3 and WAV files up to 10 MB.

```sh
python3 -m simon --live local/showcase.json
```

When audio is supplied, Gemini 4 Hydrogen creates timestamped observations. Two independent Managed Agent calls review the performance and the booking fit in parallel. A third Managed Agent compares their findings and drafts an invitation for the producer to review. The JSON includes live interaction IDs for tracing. Audio and supplied notes are sent to Gemini in live mode. Use audition IDs in the agent reports and keep artist contact details outside the manifest. A producer confirms the booking terms and contacts the artist.

- [Gemini audio understanding](https://aistudio.google.com/docs/audio)
- [Managed Agents quickstart](https://aistudio.google.com/docs/managed-agents-quickstart)
- [Antigravity agent capabilities and limitations](https://aistudio.google.com/docs/antigravity-agent#limitations)

## First showcase

1. Agree on a budget with one sponsor and one listening room. Define the room, set length, and artist guarantee.
2. Invite submissions through local open-mic hosts and music communities. Ask singers for a short take, an original song, and their live setup.
3. Run the graph and let the producer listen to the underlying takes. Use disagreements to decide which additional clip or detail to request.
4. Offer a paid slot. Track accepted bookings, show attendance, and the margin per event.

For the hackathon demo, end on the paid invitation. A willing singer and a real pilot budget make that moment concrete. The checked-in fixture demonstrates the workflow with fictional artists and an illustrative budget.
