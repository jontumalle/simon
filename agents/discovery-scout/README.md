# `simon-discovery-scout`

Curated Gemini Managed Agent (`antigravity-preview-09-2026`) that turns a **taste brief** into public YouTube search queries and candidate performer leads (`ArtistLead`), grouping clips by performer and flagging uncertain attributions.

## Input / Output Contract
- **Input**: `taste_brief` (string) + optional `target_artist` (string, used during the Thin-Evidence Second-Take Loop).
- **Output**: JSON object containing `search_queries`, `candidate_videos` (`stage_name`, `url`, `attribution_status`, `attribution_notes`), and `discovery_summary`, verified downstream by `simon.youtube.YouTubeConnector`.

## Test Commands
```sh
# Verified demo fixture
python3 -m simon scout --brief "Find singers who reinterpret familiar songs through phrasing or arrangement."

# Live Managed Agent + YouTube oEmbed + Gemini 4 Hydrogen run
python3 -m simon scout --live --brief "Stripped-back soul with distinctive phrasing"
```
