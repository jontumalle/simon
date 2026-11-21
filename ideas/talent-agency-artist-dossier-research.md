# Talent Agency, Booking & A&R Artist Profile Architecture: Industry Reality, Blind Spots & Simon's 4-Stage Agentic Schema

> **Domain & Technical Research Report for Simon**  
> **Scope**: Emerging vocalists/musicians & live showcases (*First Listen NYC* pilot), architected for extensibility to full-service talent scouting & agency pipelines.  
> **Primary Industry Reference Stack**: CAA, WME, UTA, Wasserman Music, Ground Control Touring, High Road Touring · Chartmetric, Soundcharts, Sodatone (WMG), Luminate, ROSTR, Pollstar Boxoffice, Viberate · Prism.fm, Gigwell, Overture, DISCO.ac · Jaxsta, Muso.AI, MusicBrainz · Deezer / IRCAM Amplify.

---

## Executive Overview: The Two Halves of a Real Artist Dossier

In the contemporary music business, no single tool holds a complete artist profile. Real-world talent evaluation is fractured across **five disconnected institutional silos**:
1. **A&R Telemetry Dashboards** (*Chartmetric, Soundcharts, Sodatone, Luminate, Viberate*): Track post-distribution DSP velocity, save/skip ratios, playlisting, and TikTok sound derivatives.
2. **Representation & Credits Graphs** (*ROSTR, Pollstar Directory, Jaxsta, Muso.AI, BookingAgentInfo*): Track who represents whom by territory, corporate parent, and studio/writing credits.
3. **Live Booking & Settlement ERPs** (*Pollstar Boxoffice, Prism.fm, Gigwell, Overture, Master Tour*): Track hard-ticket box office history, room capacities, GBOR/NBOR settlements, deal structures, radius clauses, and tech riders.
4. **Sync & Rights Dossiers** (*DISCO.ac, ASCAP/BMI Songview, CISAC IPI, SoundExchange*): Track master/publishing splits, ISRC/ISWC codes, IPI/CAE numbers, one-stop clearance status, and stems/instrumentals.
5. **Unstructured Human "Gut" & Scene Whisper Networks** (*Text threads with engineers, burner TikTok feeds, Mercury Lounge/Baby's All Right back-room sets, Discord demo drops*): Where actual pre-viral discovery and "it-factor" conviction happen—almost entirely unrecorded in structured databases.

**Simon's unfair advantage** is bridging Silos 1–4 with **Silo 5**: using multimodal foundation models (`gemini-4-hydrogen`) and parallel **Managed Agents** to ingest raw zero-metric performances, audit live vocal authenticity vs. studio pitch-correction, map micro-scene co-signs, and preserve multi-critic aesthetic conviction *before* an artist ever registers a Spotify Popularity Index spike.

---

## Part 1: What Real Talent Agencies, Booking Agencies & A&R Teams Actually Track Today

### How Agency & A&R Tiers Differ in Profile Emphasis

| Organization Tier | Examples | Primary Dossier Focus | Typical Signing / Action Threshold |
| :--- | :--- | :--- | :--- |
| **Major Full-Service Agencies** | **WME, CAA, UTA, Wasserman Music** | Proven hard-ticket leverage, multi-market routing, crossover brand/sync ceiling, established management + attorney buffer | Selling out 300–500+ cap rooms across multiple regions; existing mgmt/legal; scalable guarantees (\$1.5k–\$10k+/night entry) |
| **Boutique / Tastemaker Indie Agencies** | **Ground Control Touring, High Road Touring, Pitch Perfect, TBA** | Scene credibility, critical press, roster bill-pairing synergy, DIY touring grit, artistic longevity over viral stunts | Self-booked 1–2 regional runs; drawing 60–75%+ in 150–300 cap tastemaker rooms (*Baby's All Right, Mercury Lounge, Empty Bottle*); strong peer co-signs |
| **Major & Indie Label A&R** | **Republic, Interscope, Atlantic, Secretly Group, Matador, Dead Oceans** | Songwriting ceiling, vocal/sonic thumbprint, fan conversion ratios (save rate, follower/listener ratio), worldbuilding | Either high-velocity organic inflection (*Sodatone/Chartmetric*) OR deep subcultural thesis (*Mk.gee, Dijon, Ethel Cain* model) |
| **Showcase / Local Talent Buyers** | **Bowery Presents / Mercury East, Baby's All Right, Sofar Sounds, *First Listen NYC*** | Live vocal/stage delivery (video proof), local draw (NYC/borough radius), set length, tech changeover simplicity, reliability | Compelling live clip, clear local draw or curated aesthetic fit, low-friction backline/input list, fast communication |
| **Sync & Licensing Houses** | **Terrorbird, Bank Robber, Primary Wave, In-house Label Sync** | Rights hygiene (100% one-stop or pre-cleared splits), instrumental/TV stems availability, lyrical/mood searchability | Clean chain-of-title, zero uncleared samples, WAV + instrumental stems in DISCO.ac, exact IPI/ISRC/ISWC metadata |

---

### Pillar 1.1: Identity & Entity Graph
*Reference Systems: ROSTR, Jaxsta, Muso.AI, MusicBrainz, CISAC / Songview, ISO ISNI*

Agencies and labels separate the **public-facing artist project** from the **underlying human contributors, legal entities, and territorial representation stack**.

| Field Category | Concrete Schema Fields | Industry Nuance & Real Examples |
| :--- | :--- | :--- |
| **Core Identity** | `artist_id`, `primary_stage_name`, `name_aliases[]`, `pronouns`, `project_type` (`solo_vocalist` \| `duo` \| `band` \| `collective` \| `dj_producer`), `active_since_year`, `career_stage_tier` (`bedroom_diy` \| `local_buzz` \| `regional_developing` \| `national_breakout` \| `established`) | Tracks rebrands and side-projects (e.g., an indie vocalist who also topline-writes for electronic acts). |
| **Legal & Contracting Entities** | `performing_legal_names[]`, `loan_out_company_name` (e.g., *LLC / Inc.*), `entity_jurisdiction`, `tax_residency_country`, `citizenship_countries[]`, `us_work_authorization_status` (`us_citizen_or_gc` \| `o1b_active` \| `p1b_active` \| `esta_ineligible_for_paid_work` \| `requires_visa` \| `unknown`), `age_verification_flag` (`21_plus` \| `18_to_20` \| `minor_requires_guardian`) | **Critical for NYC booking**: Venue age limits (21+ bar licenses like Arlene's/Pianos late sets) and foreign artist visa status (an international viral act cannot legally play a paid *First Listen NYC* showcase without O-1/P-1 work authorization). |
| **Geography & Home Market** | `home_city`, `home_borough_or_neighborhood` (e.g., *Bushwick, Brooklyn*; *Jersey City, NJ*), `home_metro_dma`, `secondary_anchor_markets[]`, `willingness_to_travel_radius_miles` | Local buyers distinguish "NYC-based" (can bring 30 friends on a Tuesday) from "Boston-based willing to take Amtrak." |
| **Genre & Scene Taxonomy** | `primary_genre`, `subgenres[]`, `micro_scene_tags[]` (e.g., *Brooklyn bedroom R&B*, *LES sleaze rock*, *alt-gospel soul*), `sonic_comparables_comps[]` ("For Fans Of / FFO" max 3) | Agencies avoid generic tags like "Pop"; they pitch bills using **FFO comps** (e.g., *"FFO: Dijon, Lianne La Havas, Cleo Sol"*). |
| **Representation Stack (ROSTR Model)** | `management` (`company`, `primary_manager_name`, `day_to_day_manager_name`, `email`, `status`), `booking_agents[]` (`agency`, `agent_name`, `territory`: `north_america` \| `uk_eu` \| `row` \| `worldwide`, `exclusivity`), `record_label` (`name`, `parent_group`, `deal_type`: `unsigned` \| `distro_only` \| `label_services` \| `indie_licensing` \| `major_royalty`), `distributor` (e.g., *DistroKid, AWAL, Stem, Too Lost, The Orchard*), `publisher` (`name`, `deal_type`: `self_published` \| `admin_only` \| `co_pub`), `publicist_pr`, `legal_counsel`, `business_manager` | **Territorial splitting is standard**: An artist regularly has *Wasserman* for North America and *Primary Talent* or *CAA UK* for UK/Europe, or has a distributor (*AWAL*) while remaining `unsigned` for master/booking rights. |
| **Global Industry Identifiers** | `isni` (16-digit ISO standard), `ipi_cae_numbers[]` (9–11 digit CISAC composer IDs), `pro_affiliation` (`ASCAP` \| `BMI` \| `SESAC` \| `GMR` \| `PRS` \| `SOCAN` \| `none`), `soundexchange_id`, `musicbrainz_mbid`, `rostr_slug`, `chartmetric_id`, `pollstar_artist_id` | Prevents homonym collisions (two artists named "Sora") across DSPs, royalty societies, and Pollstar settlements. |
| **Collaborator & Credits Graph** | `core_band_members[]`, `frequent_producers[]`, `co_writers[]`, `session_musicians[]`, `mixing_mastering_engineers[]`, `visual_directors_photographers[]` | Powered by *Jaxsta / Muso.AI* or liner-note scraping; often the #1 early signal when an unknown vocalist works with an A-list indie engineer. |

---

### Pillar 1.2: Commercial, Streaming & Social Footprint
*Reference Systems: Chartmetric, Soundcharts, Sodatone (WMG), Luminate, Viberate, Spotify for Artists, Apple Music for Artists*

Modern A&R analysts explicitly discount raw stream totals ("vanity metrics") in favor of **intent, retention, and conversion ratios** that expose passive playlist background listening vs. active fandom.

| Metric Group | Concrete Schema Fields | Healthy / Breakout Industry Benchmarks |
| :--- | :--- | :--- |
| **DSP Reach & Velocity** | `spotify_monthly_listeners`, `spotify_followers`, `spotify_popularity_index` (`0–100`), `total_catalog_streams_luminate`, `apple_music_city_charts[]`, `shazam_total_count`, `shazam_7d_velocity_pct` | **Spotify Popularity Index (SPI)**: Crossing `~28–32` triggers algorithmic *Discover Weekly* / *Radio*; `45+` signals strong regional/national pull. **Shazam spikes** in specific cities often precede streaming spikes by 1–3 weeks. |
| **Fan Conversion & Stickiness Ratios** | `follower_to_monthly_listener_ratio` (`followers / monthly_listeners`), `streams_per_listener_28d`, `save_rate_pct` (`saves / unique_listeners`), `playlist_add_rate_pct`, `skip_rate_under_30s_pct`, `completion_rate_pct` | **Save Rate**: `<1%` = passive/mismatch/botted; `3–5%` = healthy emerging; `6–10%+` = high-conviction A&R alert.<br>**Follower-to-Listener Ratio**: `<1.5%` = passive mood-playlist inflation; `5–12%+` = dedicated cult fanbase.<br>**Skip Rate**: `>25–30%` kills algorithmic lift; **Completion Rate** `>55%` sustains *Release Radar* & *Discover Weekly*. |
| **Playlist Ecosystem Mix** | `editorial_playlists_count`, `algorithmic_stream_share_pct`, `active_stream_share_pct` (searches, artist profile plays, user library), `third_party_playlist_risk_score` (`0.0–1.0` bot/payola fraud check) | A&Rs inspect **Active vs. Programmed Stream Share**: if `85%` of streams come from one shady third-party playlist with spiking 1-day listener cliffs in random cities, it is flagged as artificial streaming. |
| **Geographic Demand ("Trigger Cities")** | `top_listener_cities[]` (`city`, `country`, `monthly_listeners`, `7d_growth_pct`, `listener_per_capita_index`), `home_market_listener_share_pct` | *Chartmetric* calls sudden localized growth hubs **Trigger Cities**; booking agents match city listener clusters directly against 150–300 cap routing maps. |
| **Short-Form & Social Forensics** | `tiktok_followers`, `tiktok_official_sound_creations_count`, `tiktok_median_views_last_10_posts`, `ig_followers`, `ig_engagement_rate_pct`, `ig_saves_and_shares_ratio`, `youtube_subscribers`, `soundcloud_reposts_velocity`, `bandcamp_supporters_count`, `mailing_list_or_sms_subscribers` (*Laylo / Seated / Community*) | **Sodatone distinction**: Separates *views on the artist's own post* vs. *organic UGC sound creations* by strangers, and tracks **D2C owned audience** (*Bandcamp paying supporters, Laylo RSVP drops*) which converts `10x` better to hard tickets than TikTok followers. |
| **Catalog & Release Hygiene** | `released_tracks_count`, `isrcs[]`, `release_cadence_days_avg`, `last_release_date`, `unreleased_demo_vault_estimate`, `top_track_stream_concentration_pct` (`top_1_track_streams / catalog_streams`) | If `top_track_stream_concentration_pct > 92%` across a 10-song catalog, A&Rs flag "one-song viral anomaly" risk unless recent follow-ups show strong save rates. |

---

### Pillar 1.3: Live, Touring & Booking Economics
*Reference Systems: Pollstar Boxoffice, Prism.fm, Gigwell, Overture, Master Tour, Bandsintown Pro, Dice.fm*

For booking agencies (WME, CAA, UTA, Wasserman, Ground Control, High Road) and showcase producers (*First Listen NYC*), **streaming metrics do not pay venue rent—hard tickets and room execution do.**

| Live Dimension | Concrete Schema Fields | Industry Terminology & Mechanics |
| :--- | :--- | :--- |
| **Ticket Type & Draw History** | `hard_ticket_shows_count`, `soft_ticket_shows_count` (festivals, free college/brand events, multi-band bar nights), `pollstar_avg_tickets_sold`, `pollstar_avg_gross_usd`, `sellout_rate_pct`, `walkup_vs_advance_ticket_ratio`, `no_show_drop_rate_pct` | **Hard Ticket vs. Soft Ticket**: A **hard ticket** means a fan paid \$15–\$35 specifically to see *this* artist's name at the top of the marquee. Selling 180 hard tickets at *Mercury Lounge* is worth more to an agent than playing to 2,000 passive passersby at a free street fair. |
| **Market-by-Market Room Ladder** | `market_draw_records[]` (`city`, `venue_name`, `venue_cap`, `billing_position`: `headline` \| `co_headline` \| `direct_support` \| `opener` \| `showcase_slot`, `date`, `paid_attendance`, `comp_list_count`, `ticket_price_usd`, `promoter_name`) | **NYC Venue Tier Ladder**:<br>• *Tier 0 (Listening / Open / DIY)*: Sofar Sounds, Pete's Candy Store, Berlin Under A, backyard/loft spaces (`40–100 cap`)<br>• *Tier 1 (Grassroots Local)*: Arlene's Grocery, Pianos Upstairs/Showroom, Heaven Can Wait, Our Wicked Lady (`120–200 cap`)<br>• *Tier 2 (Breakthrough Tastemaker)*: Mercury Lounge (`250 cap`), Baby's All Right (`280–300 cap`), Union Pool, Night Club 101, Zone One @ Elsewhere<br>• *Tier 3 (Milestone Club)*: Bowery Ballroom (`575 cap`), Music Hall of Williamsburg (`650 cap`), Le Poisson Rouge (`700 cap`). |
| **Deal Structures & Settlement Economics** | `typical_deal_type` (`flat_guarantee` \| `versus_deal` \| `plus_deal` \| `door_split` \| `promoter_profit_split` \| `showcase_honorarium`), `guarantee_floor_usd`, `backend_split_pct` (e.g., `85%` over split point), `settlement_basis` (`NBOR` vs `GBOR`), `merch_per_head_usd`, `venue_merch_cut_pct` (`0–20%`), `active_radius_clauses[]` (`miles`, `days_before`, `days_after`, `anchor_event`) | **GBOR vs. NBOR**: Gross Box Office Receipts minus taxes/facility fees = Net Box Office Receipts.<br>**Versus Deal**: e.g., `\$1,000 vs. 85% NBOR after approved expenses` (artist gets whichever is higher above the **split point**).<br>**Radius Clause**: Prevents booking an artist if they are locked out by e.g. Governors Ball or a nearby Bowery show within `60 miles / 60 days`. |
| **Touring Infrastructure & Self-Sufficiency** | `self_booked_tours_completed`, `support_tours_completed` (`headliner_name`, `dates_count`, `paid_support_vs_buy_on`), `touring_party_size_total` (`musicians_count` + `crew_count`), `break_even_daily_nut_usd` | Indie agencies (*Ground Control, High Road*) prize acts with a lean **daily nut**: a solo/duo act with a touring party of 2–3 breaks even in 200-cap clubs, whereas a 7-piece band with FOH engineer bleeds cash until 800-cap rooms. |
| **Live Configuration & Tech Rider Complexity** | `live_setup_format` (`solo_acoustic` \| `solo_vocal_plus_tracks` \| `duo_hybrid` \| `full_live_band` \| `band_plus_ableton_rig`), `input_channels_count`, `requires_iem_rig` (in-ear monitors), `backline_shareable` (`bool`), `changeover_minutes_estimate`, `set_lengths_ready_minutes[]` (`15`, `30`, `45`, `60`), `tech_rider_url`, `stage_plot_url` | **Crucial for *First Listen NYC***: Multi-artist showcases live or die on `10–15 minute` changeovers and shared house backline. A vocalist who can command a room with a single vocal mic + acoustic guitar/keys or clean stereo DI stems has `10x` higher showcase bookability than an unhinged 18-channel setup with zero stage plot. |

---

### Pillar 1.4: Brand, Press, Sync & Cultural Context
*Reference Systems: DISCO.ac, Hype Machine, Pitchfork / OnesToWatch / Pigeons & Planes / Stereogum, Radio Charts (NACC College Radio, KEXP, BBC Radio 1)*

| Context Area | Concrete Schema Fields | Why Industry Buyers Care |
| :--- | :--- | :--- |
| **Tastemaker & Peer Co-Signs** | `press_mentions[]` (`outlet`, `tier`, `author`, `url`, `quote_snippet`), `college_public_radio_spins` (*NACC Top 200, KEXP, WFUV, WXPN, NTS*), `artist_co_signs[]` (`co_signing_artist`, `interaction_type`: `playlist_share` \| `comment` \| `stage_guest` \| `repost` \| `studio_session`) | A single repost or studio tag from *Dijon, Blood Orange, Kaytranada, Phoebe Bridgers,* or * Zane Lowe* carries higher A&R signal weight than 250k passive TikTok views. |
| **Sync & Licensing Readiness (DISCO Dossier)** | `one_stop_clearance_ready` (`bool` — 100% master + 100% publishing controllable in one signature), `easy_clear_contacts_verified` (`bool`), `contains_samples_or_interpolations` (`bool`), `instrumentals_and_stems_available` (`bool`), `clean_radio_edits_available` (`bool`), `sync_mood_tags[]`, `sync_lyrical_themes[]`, `past_sync_placements[]` | In TV/film/brand trailers, clearance speed wins deals. Emerging independent vocalists who own 100% of their master + publishing (`one_stop = true`) with clean WAV + instrumental versions can land \$5k–\$50k sync fees immediately. |
| **Audience Demographics & Brand Fit** | `audience_age_brackets`, `audience_gender_skew`, `subcultural_affinities[]` (fashion, skate, queer nightlife, gospel/faith, art school, anime/gaming), `brand_safety_flags[]`, `brand_partnership_history[]` | Used by CAA/UTA/WME brand partnerships teams and festival curators to pair artists with sponsors (e.g., * Converse, Dr. Martens, A24, SSENSE*). |
| **Artist Narrative & Worldbuilding** | `elevator_pitch_one_liner`, `origin_story_hook`, `visual_identity_motifs[]`, `fan_community_rituals[]`, `epk_or_press_kit_url` | Separates generic singers from cultural magnets (*Chappell Roan* dress-code camp universe; *Mk.gee* tactile analog mystique). |

---

## Part 2: What Scouts, Booking Agents & A&Rs WISH They Had (Pain Points Newly Solvable by Multimodal AI + Autonomous Agents)

Every major label and agency now pays for *Chartmetric*, *ROSTR*, and *Pollstar*. Because everyone stares at the exact same dashboards, **traditional data-driven A&R has commoditized itself**: when a track crosses Sodatone's velocity threshold, 15 junior A&Rs DM the artist on the same Tuesday, inflating advances while completely missing true ground-floor talent—or signing viral mirages who implode on stage.

Below are the **four massive industry blind spots** that human teams could never scale manually, which **Multimodal AI (`gemini-4-hydrogen`) + Autonomous Managed Agents** unlock for the first time.

---

### Blind Spot 2.1: Pre-DSP / "Zero-Metric" & Hyper-Local Scene Discovery
* **The Human Pain Point**: Chartmetric, Soundcharts, and Luminate are **post-distribution lagging indicators**. An artist with 0 Spotify tracks—or 400 monthly listeners—is invisible to enterprise A&R software, even if they are packing 120 people into a Bushwick loft, singing jaw-dropping unrehearsed vocals at a Harlem open mic, or posting raw voice-memo snippets on a 300-follower IG account. Human scouts use "burner TikTok accounts" to hunt zero-like clips or walk LES clubs nightly, which cannot scale past a few dozen evaluations a week.
* **What Multimodal + Agentic Discovery Unlocks**:
  1. **Flyer & Event Lineup OCR + Entity Extraction**: Autonomous agents scrape local independent venue calendars (*Dice.fm, Shotgun, Resident Advisor, Partiful public flyers, Sofar city recaps, Arlene's/Pianos/Baby's IG flyer posts*), use multimodal vision to read stylized DIY show flyers, and build a longitudinal graph of **who keeps getting booked on local co-bills** 6 months before Pollstar ever records a ticket.
  2. **Reverse Session/Backing-Musician Graph Mining**: Often the best vocalist in NYC hasn't launched a solo Spotify page yet—they are tagged in IG stories singing background vocals (`BGVs`) for three rising Brooklyn bands, graduating from Clive Davis / Berklee / New School jazz vocal programs, or leading runs in local church/gospel choirs. Agents traverse `@mentions` in live clips and credits to surface unlaunched solo stars.
  3. **Zero-Follower Raw Clip Discovery**: Searching acoustic/unreleased tags (`#unreleasedmusic`, `#openmicnyc`, `#tinysdeskcontest`, `#singersongwriter`, `#voicecheck`, Bandcamp `new york` arrival tags, SoundCloud demo repost chains) and evaluating **the audio/video directly** without filtering on view count.

---

### Blind Spot 2.2: Deep Multimodal Media Digestion (Audio + Video + Lyrics)
* **The Human Pain Point ("The Studio-to-Stage Catfish & AI Slop Flood")**:
  - **The Live Vocal Reality Check**: Dozens of viral TikTok signings over the past 3 years collapsed on their first festival or club tour because their "signature sound" was heavy Melodyne pitch-flattening, Vocalign micro-timing grid snaps, and 16 stacked whisper-vocal tracks that could not project over a live snare drum.
  - **The Generative AI Flood**: By 2025–2026, DSPs like Deezer reported **50%+ of daily incoming uploads** during peak windows were synthetic *Suno/Udio* tracks tied to streaming fraud. Even more subtle are "hybrid" tracks where a human pastes AI vocals over a beat.
  - **Listening Fatigue**: A human scout listening to 200 submissions skips within 8 seconds and cannot systematically log spectral, timbral, rhythmic, and visual observations across every clip.
* **What Multimodal AI (`gemini-4-hydrogen` Native Audio + Video) Unlocks**:
  1. **Live-vs-Studio Delta (`live_vs_studio_vocal_delta`)**: Comparing a raw phone/room live clip against a studio release (or auditing a single live clip) across:
     - **Pitch Center & Intonation Recovery**: Does the singer have true pitch center and natural vibrato transitions, or audible Melodyne formant flattening / robotic step-artifacts? When they go slightly flat in a live room, do they *hear and correct it in real time* (ear/musicianship proof)?
     - **Breath Support, Projection & Register Transitions**: Chest-to-head voice (`passaggio`) control, sustained belt stability vs. breath exhaustion after 90 seconds, mic technique (pulling back on high transients).
     - **Pocket & Micro-Timing**: Whether phrasing locks intentionally behind/ahead of the beat vs. dragging unintentionally when stripped of DAW quantization.
     - **Lip-Sync & Heavy Playback Detection**: Auditing acoustic bleed in room audio, mouth transient alignment on plosives (`p/b/t`), breath alignment with physical movement, and whether the "live" vocal has identical dynamic compression to a pre-recorded stem.
  2. **Timbral Signature & 3-Second "Scroll-Stop" Distinctiveness**: Describing the acoustic grain/formant character of the voice (e.g., *smoky alto rasp with agile neo-soul upper extension*) and testing whether it sounds derivative of 1,000 Billie Eilish / Tate McRae clones vs. possessing an unmistakable vocal "face."
  3. **Room-Audio Crowd Forensics**: In live showcase clips, listening *past* the artist to the room: did bar chatter quiet down between verse 1 and chorus 1 ("the hush effect")? Were audience cheers polite 3-person claps or visceral mid-run reactions?
  4. **Songwriting Hook Density & Lyrical Specificity**: Measuring time-to-first-hook, melodic interval memorability, and whether lyrics use concrete sensory imagery vs. generic LLM/cliché filler (*"neon lights / shadows in the night"*).
  5. **Synthetic / Suno-Udio Authenticity Verification**: Flagging neural vocoder phase smear, upper-frequency spectral cutoffs, unnatural breathlessness, and verifying *embodied human performance* via cross-modal video verification.

---

### Blind Spot 2.3: High-Signal Qualitative & Relational Metadata Forensics
* **The Human Pain Point**: Analytics platforms count *how many* comments a post got (`comment_count = 142`), which is trivially gamed by engagement pods, bots, or rage-bait memes. Human scouts manually open comment drawers to check *who* commented and *what* they asked—a slow, manual forensic check. Meanwhile, agencies waste hours discovering too late that an exciting artist is already locked into a shadow 360 deal or never answers emails.
* **What Autonomous Scouting Agents Unlock**:
  1. **Comment-Section Semantic & Identity Forensics**:
     - **Pull Intent vs. Meme Amusement**: Classifying comments into **Purchase/Streaming Pull** (*"DROP THIS ON SPOTIFY NOW"*, *"what's the song name??"*, *"need tickets when u come to nyc"*), **Emotional Identification** (*"this made me cry on the L train"*), **Peer/Industry Co-Signs** (verified or bio-identified producers, photographers, club bookers, other indie musicians commenting *"check DM"* or fire emojis), vs. **Ironic/Meme Noise** (people laughing at a background mishap with zero care for the music) or **Bot Pod Spam** (generic *"Great vibe! Check out my bio"*).
  2. **Representation White-Space Detection ("Deal-Flow Arbitrage")**:
     - Cross-referencing IG/TikTok bio strings, Linktree/Beacons endpoints, Spotify "About" text, Songview PRO registrations, and SoundCloud/Bandcamp footers to detect **asymmetric representation gaps**—e.g., *"Artist has 45k engaged IG followers, a manager at a boutique firm, AWAL distribution, and 3 sold-out LA shows, **but ZERO North American booking agent and self-administered publishing**."* For an agency or showcase booker, white-space detection is pure gold.
  3. **Operational & Booking Reliability Signals**:
     - Does the artist have a working contact route, clear location metadata, past punctual show appearances without chronic cancellation posts, and coherent visual assets?

---

### Blind Spot 2.4: Agentic "Taste", Standout Calibration & Disagreement Preservation
* **The Human Pain Point ("Consensus Mediocrity vs. Polarizing Stars")**:
  - Single-score leaderboards (`AI Heat Score = 84/100`) fail catastrophically at art. When you average scores across safe criteria, **competent, derivative conservatory singers score `7.8/10` across the board**, while generational stars (*Chappell Roan* early camp era, *Mk.gee*, *Björk*, *Young Thug*, *Amy Winehouse*) polarize rooms (`9.5` on distinctiveness/worldbuilding from one scout, `5.5` on conventional polish or tech friction from another).
  - Furthermore, "good" is meaningless without **Thesis Calibration**: an artist who is a `9/10` for *First Listen NYC* (intimate 150-cap vocal-forward room, 20-minute stripped set) might be a `4/10` for a late-night warehouse rave, and vice versa.
* **What Multi-Agent Critique + Producer Synthesis Unlocks**:
  1. **Adversarial / Orthogonal Specialist Critics (Not One Monolithic LLM)**:
     - **Vocal & Sonic Critic**: Obsessed purely with timbre, phrasing, songwriting craft, emotional conviction, and live vocal truth—blind to follower counts.
     - **Scene & Cultural Strategist**: Evaluates subcultural whitespace, worldbuilding, peer co-signs, visual magnetism, and "meme vs. career" durability.
     - **Live Booking & Production Validator**: Evaluates room cap fit, NYC draw plausibility, changeover friction, visa/age/radius blockers, and realistic guarantee/honorarium tier.
     - **Skeptic / Red-Team Auditor**: Specifically hunts for studio-to-live vocal gaps, bot/playlist inflation, derivative trends, AI audio tells, or one-hit gimmick risk.
  2. **Disagreement Preservation (`conviction_variance`)**:
     - Instead of averaging away conflict, Simon records **structured dissent**: high variance with at least one `9+/10` high-conviction champion triggers an **"A&R Debate / Must-Watch Audition"** flag rather than losing to a bland `7.5` consensus act.
  3. **Configurable Roster / Venue Thesis Lens**:
     - Separates **Intrinsic Artistry Signals** from **Target Venue/Agency Fit** (*First Listen NYC* acoustic showcase vs. *Ground Control* indie touring roster vs. *Sync One-Stop* catalog).

---

## Part 3: Concrete Schema & Architecture Mapping to Simon's 4-Stage Agentic Pipeline

Below is a production-ready, schema-explicit blueprint mapping every industry field and AI capability across the 4 sequential/parallel stages of Simon's Managed Agent pipeline.

```
[Raw Sources: Local Flyers, IG/TikTok/YT Clips, Open Mics, Bandcamp, Submissions]
                                      │
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ STAGE 1: Discovery & Basic Profile Agent (Pre-Media Triage)             │
 │ Fast entity resolution, zero-metric discovery provenance, contact/bio   │
 │ parsing, representation snapshot, legal/geography gatekeeping.          │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ (Passes candidate + raw media URIs)
                     ┌────────────────┴────────────────┐
                     ▼                                 ▼
 ┌───────────────────────────────────────┐ ┌───────────────────────────────┐
 │ STAGE 2: Multimodal Media Digestion   │ │ STAGE 3: Scout Metadata       │
 │ (`gemini-4-hydrogen` Audio+Video)     │ │ Enrichment Agent              │
 │ Timbre, live-vs-studio delta, pitch   │ │ DSP ratios, Pollstar/room     │
 │ correction audit, pocket, room hush,  │ │ ladder, comment forensics,    │
 │ hook density, AI-slop authenticity.   │ │ credits graph, rep whitespace.│
 └───────────────────┬───────────────────┘ └───────────────┬───────────────┘
                     └────────────────┬────────────────────┘
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ STAGE 4: The "Taste" & Standout Pipeline (Multi-Critic + Producer)      │
 │ Parallel Specialist Critics (Artistry, Cultural Thesis, Live Pragmatics,│
 │ Red-Team Skeptic) → Disagreement Preservation → Star/Callback Synthesis │
 │ → `pending_human_review` Showcase Offer / Agency Brief.                 │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

### Stage 1: Discovery & Basic Profile (Pre-Media Digestion)

**Goal**: Ultra-fast, low-cost structural ingestion before spending heavy multimodal token budgets or external enrichment queries. Resolves *who* the artist is, *how* they surfaced, *where* they are based, and whether basic hard gates (geography, human project, non-duplicate) pass.

#### Stage 1 Schema (`DiscoveryBasicProfile`)
```json
{
  "schema_version": "1.0.0",
  "artist_id": "art_nyc_0194f2a",
  "ingested_at": "2026-11-21T18:00:00Z",
  "discovery_provenance": {
    "source_channel": "diy_venue_flyer_ocr | tiktok_raw_clip | ig_reel_bgv_tag | bandcamp_local_tag | soundcloud_repost | open_mic_capture | direct_opt_in_submission",
    "discovery_seed_query_or_node": "@babysallright flyer 2026-11-14 opener slot #1",
    "source_urls": ["https://..."],
    "zero_metric_candidate": true,
    "opt_in_or_public_status": "public_performance_clip | artist_opt_in_submission"
  },
  "identity": {
    "primary_stage_name": "Maya Vance",
    "name_aliases": ["mayavancevocal"],
    "project_type": "solo_vocalist",
    "pronouns": "she/her",
    "career_stage_tier": "local_buzz",
    "home_city": "Brooklyn",
    "home_neighborhood": "Bed-Stuy",
    "home_metro_dma": "New York, NY",
    "age_gate_estimate": "21_plus_verified_venue_history",
    "us_work_authorization_signal": "domestic_nyc_resident_likely"
  },
  "taxonomy_initial": {
    "primary_genre": "Alternative R&B / Neo-Soul",
    "subgenres": ["Acoustic Soul", "Indie Gospel-Inflected Pop"],
    "micro_scene_tags": ["Brooklyn live-room vocalists", "Clive Davis / NYU session circle"],
    "self_described_bio_raw": "bklyn. singing in rooms near u. mgmt: none / bookings: dm or email"
  },
  "platform_handles": {
    "instagram": "@mayavance...",
    "tiktok": "@mayavance...",
    "youtube": "https://youtube.com/@...",
    "spotify_artist_id": null,
    "apple_music_id": null,
    "soundcloud_url": "https://soundcloud.com/...",
    "bandcamp_url": null,
    "personal_site_or_linktree": "https://linktr.ee/..."
  },
  "routing_and_contact_gate": {
    "public_business_inquiry_route_exists": true,
    "contact_channel_type": "public_bio_email | management_email | ig_open_dm | submission_form",
    "private_pii_vault_ref": "local://vault/contacts/art_nyc_0194f2a.json",
    "initial_rep_flags": {
      "appears_unsigned": true,
      "appears_unagented": true,
      "management_listed": false
    }
  },
  "candidate_media_queue": [
    {
      "media_id": "med_01",
      "media_type": "live_phone_video",
      "recording_context": "live_club_room",
      "venue_if_known": "Pianos Upstairs NYC",
      "duration_sec": 74,
      "uri": "local://clips/maya_pianos_live.mp4"
    },
    {
      "media_id": "med_02",
      "media_type": "studio_or_demo_audio",
      "recording_context": "bedroom_acoustic_voice_memo",
      "duration_sec": 142,
      "uri": "local://clips/maya_unreleased_demo.m4a"
    }
  ],
  "stage_1_triage_decision": "advance_to_multimodal_digestion"
}
```
*Governance Note*: Per Simon's `pm/scope.md` guardrails, raw personal emails/phone numbers are never written to public manifests—only `private_pii_vault_ref` pointers inside gitignored `local/` storage.

---

### Stage 2: Multimodal Media Digestion (Audio / Video / Lyrics / Visuals)

**Goal**: Run `gemini-4-hydrogen` directly on raw audio and video performance artifacts to extract **structured acoustic, vocal, songwriting, live-room, and visual evidence** with exact timestamp citations (`MM:SS–MM:SS`). This stage is **strictly metric-blind** so follower counts cannot bias what the model hears and sees.

#### Stage 2 Schema (`MultimodalMediaDigestion`)
```json
{
  "artist_id": "art_nyc_0194f2a",
  "analyzed_media_ids": ["med_01", "med_02"],
  "authenticity_and_ai_audit": {
    "human_performance_confidence": 0.98,
    "generative_ai_music_risk": "negligible",
    "ai_artifact_checks": {
      "suno_udio_spectral_smear_detected": false,
      "embodied_lip_and_breath_sync_verified": true,
      "live_lead_vocal_vs_playback_verdict": "100_pct_live_lead_vocal_no_backing_track"
    },
    "pitch_correction_audit": {
      "studio_clip_tuning_level": "none_raw_room_capture",
      "live_clip_tuning_pedal_detected": false,
      "melodyne_formant_flattening_artifacts": false
    }
  },
  "vocal_craft_decomposition": {
    "vocal_timbre_signature": {
      "descriptors": ["warm chest-dominant contralto", "velvet smoky grain", "clean whistle/head-voice float"],
      "three_second_scroll_stop_distinctiveness": 9.1,
      "sonic_kinship_blind_audio": ["Lianne La Havas", "Jazmine Sullivan (stripped register)", "Olivia Dean"]
    },
    "technical_and_expressive_control": {
      "pitch_center_accuracy": 8.7,
      "real_time_intonation_recovery_evidence": "At 00:48 on a high C#5 leap over noisy bar bleed, lands slightly under pitch and micro-adjusts into dead-center resonance within 200ms.",
      "passaggio_register_transitions": 9.0,
      "breath_support_and_stamina": 8.6,
      "phrasing_and_pocket_microtiming": {
        "score": 9.3,
        "style": "laid_back_behind_the_grid",
        "timestamp_evidence": "00:19-00:34: Delays entrance of pre-chorus syllables by an eighth-note triplet against acoustic guitar thumb-slap, creating magnetic tension."
      },
      "dynamic_arc_and_emotional_conviction": 9.4
    },
    "live_vs_studio_vocal_delta": {
      "delta_direction": "live_exceeds_or_matches_recorded",
      "delta_score": +0.8,
      "notes": "Live club clip has greater dynamic danger and chest resonance than bedroom voice memo; zero studio-catfish risk."
    }
  },
  "songwriting_and_musicality": {
    "original_material_verified": true,
    "time_to_first_melodic_hook_sec": 11,
    "hook_memorability_score": 8.5,
    "harmonic_sophistication": "extended_jazz_soul_voicings_accessible_topline",
    "lyrical_audit": {
      "verbatim_standout_lines": [
        {
          "timestamp": "00:36-00:44",
          "lyric": "Left my spare keys in your radiator cup / whole sixth floor smelled like burnt cinnamon and giving up"
        }
      ],
      "specificity_vs_cliche_score": 9.2,
      "generic_ai_lyric_tells_detected": false
    }
  },
  "stage_visual_and_room_forensics": {
    "live_configuration_observed": {
      "format": "solo_vocal_and_electric_hollowbody_guitar",
      "onstage_personnel_count": 1,
      "estimated_input_channels": 2,
      "estimated_changeover_minutes": 5
    },
    "stage_magnetism_and_command": {
      "eye_contact_and_posture": "Relaxed, unhurried command; smiles mid-run without losing breath support.",
      "visual_aesthetic_coherence": 8.4
    },
    "crowd_and_room_audio_reaction": {
      "room_chatter_hush_effect_detected": true,
      "hush_evidence_timestamp": "00:14-00:28 (ambient bar glass clinking and chatter drop ~12dB after opening vocal run)",
      "spontaneous_mid_song_vocal_reactions": 3,
      "end_of_clip_applause_intensity": "visceral_local_room_eruption"
    }
  }
}
```

---

### Stage 3: Scout Metadata Enrichment (Commercial, Live, Network, Rep & Audience Forensics)

**Goal**: Enrich the candidate with cross-platform telemetry, live venue history, collaborator network centrality, representation white-space analysis, and comment-section semantic forensics. Crucially, Stage 3 normalizes for **Data Sparsity** so a zero-Spotify artist isn't penalized with `0`s—instead distinguishing `"not_yet_distributed"` from `"distributed_with_poor_conversion"`.

#### Stage 3 Schema (`ScoutMetadataEnrichment`)
```json
{
  "artist_id": "art_nyc_0194f2a",
  "data_footprint_regime": "pre_dsp_underground | early_dsp_inflection | established_streaming",
  "commercial_and_streaming_telemetry": {
    "is_on_dsps": true,
    "released_tracks_count": 2,
    "isrcs": ["USQX92601422", "USQX92602910"],
    "spotify_metrics": {
      "monthly_listeners": 4820,
      "followers": 690,
      "follower_to_listener_ratio_pct": 14.3,
      "popularity_index_0_100": 19,
      "streams_per_listener_28d": 3.8,
      "estimated_save_rate_tier": "high_organic_above_7pct",
      "top_track_concentration_pct": 64.0,
      "playlist_fraud_or_bot_risk": 0.03
    },
    "geographic_trigger_cities": [
      {"city": "Brooklyn / New York, US", "listeners": 1940, "share_pct": 40.2},
      {"city": "London, GB", "listeners": 410, "share_pct": 8.5},
      {"city": "Philadelphia, US", "listeners": 290, "share_pct": 6.0}
    ],
    "d2c_and_underground_pull": {
      "bandcamp_supporters_count": 47,
      "soundcloud_repost_to_play_ratio_pct": 6.2,
      "shazam_28d_spikes": []
    }
  },
  "audience_and_comment_forensics": {
    "posts_sampled_count": 8,
    "total_comments_analyzed": 312,
    "engagement_to_follower_ratio_pct": 11.8,
    "comment_intent_distribution": {
      "release_or_streaming_demand_pct": 34.0,
      "live_show_or_city_request_pct": 18.5,
      "visceral_emotional_praise_pct": 31.0,
      "peer_musician_producer_cosign_pct": 9.5,
      "meme_or_off_topic_joke_pct": 2.0,
      "bot_or_pod_spam_pct": 5.0
    },
    "high_signal_comment_receipts": [
      {
        "author_handle": "@producer_k_brooklyn",
        "author_credibility": "Credited mixer on 2 Secretly Group releases (Muso.AI verified)",
        "text": "voice is unreal. check dm whenever you're cutting next"
      },
      {
        "author_handle": "@fan_acct_92",
        "author_credibility": "Local NYC listener",
        "text": "saw you open at Pianos Tuesday and literally stayed for your whole set, pls put radiator song on spotify"
      }
    ]
  },
  "live_and_booking_dossier": {
    "highest_nyc_venue_tier_played": "tier_1_grassroots_local",
    "verified_show_history": [
      {
        "date": "2026-10-15",
        "venue": "Pianos Upstairs",
        "city": "New York, NY",
        "venue_cap": 150,
        "billing": "opener_of_3",
        "ticket_type": "hard_ticket_co_bill",
        "estimated_room_fill_pct": 75
      },
      {
        "date": "2026-09-22",
        "venue": "Sofar Sounds Bushwick",
        "city": "Brooklyn, NY",
        "venue_cap": 65,
        "billing": "showcase_slot",
        "ticket_type": "curated_listening_room",
        "estimated_room_fill_pct": 100
      }
    ],
    "estimated_standalone_nyc_hard_ticket_draw": {"low": 35, "mid": 55, "high": 80},
    "active_radius_clause_conflict": false,
    "booking_economics_estimate": {
      "current_market_deal_tier": "door_split_or_paid_showcase_honorarium",
      "fair_showcase_slot_fee_range_usd": [200, 450],
      "touring_party_size": 1,
      "backline_and_tech_friction": "minimal_plug_and_play"
    }
  },
  "network_and_representation_whitespace": {
    "representation_matrix": {
      "manager": {"status": "unrepresented", "confidence": 0.92},
      "booking_agent_na": {"status": "unrepresented", "confidence": 0.97},
      "record_label": {"status": "self_released_via_distrokid", "confidence": 0.95},
      "publisher": {"status": "self_published_unadministered", "confidence": 0.88},
      "pro_registration": {"society": "BMI", "ipi_found": true}
    },
    "sync_one_stop_likelihood": {
      "is_likely_100pct_one_stop": true,
      "rationale": "Solo writer credit on BMI Songview + self-released master PH/C line ('2026 Maya Vance')."
    },
    "collaborator_centrality_signals": [
      "Sang live BGVs for 2 Baby's All Right sold-out indie soul acts in Summer 2026",
      "Shared rehearsal clips with rhythm section from Clive Davis Institute cohort"
    ],
    "whitespace_opportunity_flags": [
      "HIGH_PRIORITY_UNAGENTED_NYC_LIVE_DRAW",
      "ONE_STOP_SYNC_READY_CATALOG"
    ]
  }
}
```

---

### Stage 4: The "Taste" & Standout Pipeline (Multi-Agent Critique, Thesis Calibration & Disagreement Preservation)

**Goal**: Replicate an elite A&R + Booking Agency partner meeting—**not** a bland average score. Four orthogonal Managed Agents evaluate the Stage 1–3 evidence independently, challenge each other, calibrate against the active **Target Thesis Profile** (e.g., *First Listen NYC Intimate Vocal Showcase* vs. *Boutique Indie Touring Agency Signing*), explicitly preserve aesthetic/commercial disagreement, and produce an evidence-backed Producer Decision Brief marked `pending_human_review`.

#### The 4 Orthogonal Stage-4 Critic Roles
1. **`critic_vocal_artistry` (The Pure Ear)**: Sees **only** Stage 2 Multimodal Media Digestion (blinded to followers/streams). Scores vocal DNA, songwriting ceiling, live-vs-studio truth, and emotional goosebump conviction.
2. **`critic_cultural_whitespace` (The Scene & Star Strategist)**: Evaluates worldbuilding, peer co-signs, comment-section pull vs. meme decay, visual magnetism, and *"Why does culture need this artist right now?"*
3. **`validator_live_booking` (The Talent Buyer / Agent)**: Evaluates hard-ticket draw realism, room-cap match, changeover/tech friction, legal/visa/radius readiness, and fair compensation economics for the target event/roster.
4. **`critic_red_team_skeptic` (The Devil's Advocate)**: Explicitly tasked with steelmanning why the signing/booking could **fail** (e.g., derivative comps, weak chorus payoff despite great tone, tiny catalog, passive audience, or logistical risk).

#### Why Disagreement Preservation Matters (Star Math)
Real A&R breakthroughs exhibit **high peak conviction**, often paired with fixable friction:
- **Consensus Mediocrity Trap**: Scores `[7.4, 7.2, 7.6, 7.3]` → Mean `7.38`, StdDev `0.17` → Competent background music; audiences politely clap and buy zero merch.
- **Polarizing Breakout Star**: Scores `[9.5 (Vocal), 9.1 (Cultural), 6.2 (Early Catalog/Draw), 6.8 (Skeptic)]` → High Peak Conviction (`9.5`), High Fixable Gap (needs a 150-cap showcase room like *First Listen NYC* to convert raw magic into live proof!).

#### Stage 4 Schema (`TasteAndStandoutAssessment`)
```json
{
  "artist_id": "art_nyc_0194f2a",
  "target_thesis_id": "first_listen_nyc_paid_vocal_showcase_2026",
  "independent_critic_ballots": [
    {
      "agent_role": "critic_vocal_artistry",
      "blind_to_commercial_metrics": true,
      "score_0_10": 9.3,
      "conviction_tier": "table_pounding_yes",
      "thesis_statement": "Rare chest-to-head contralto grain with zero tuning crutches; commands an actual hush in a noisy LES bar within 15 seconds.",
      "evidence_refs": ["med_01@00:14-00:34", "med_01@00:48"]
    },
    {
      "agent_role": "critic_cultural_whitespace",
      "blind_to_commercial_metrics": false,
      "score_0_10": 8.8,
      "conviction_tier": "strong_yes",
      "thesis_statement": "Fills the post-Dijon / Lianne La Havas intimate NYC acoustic-soul lane with literary NYC-specific lyricism; 14.3% Spotify follower/listener conversion and verified Brooklyn producer co-signs prove cult gravity, not meme luck.",
      "evidence_refs": ["med_01@00:36-00:44", "comment_receipts[0]"]
    },
    {
      "agent_role": "validator_live_booking",
      "blind_to_commercial_metrics": false,
      "score_0_10": 9.1,
      "conviction_tier": "strong_yes",
      "thesis_statement": "Ideal First Listen NYC fit: Brooklyn-based, 35–55 organic local draw, 2-channel solo guitar+vocal setup with 5-minute changeover, zero radius conflicts, completely unagented.",
      "evidence_refs": ["verified_show_history[0]", "live_configuration_observed"]
    },
    {
      "agent_role": "critic_red_team_skeptic",
      "blind_to_commercial_metrics": false,
      "score_0_10": 6.9,
      "conviction_tier": "cautious_watch",
      "risk_flags": [
        "Only 2 officially released tracks on DSPs—verify she has 25–30 minutes of original live material ready for a showcase slot.",
        "Solo guitar arrangement could feel dynamically uniform across a 30-minute set without one uptempo or rhythm-section moment."
      ],
      "mitigation_questions_for_human_producer": [
        "Confirm total minutes of original live set currently rehearsed (20 min vs 30 min).",
        "Ask if she prefers performing solo hollowbody guitar or bringing upright bass/cajon duo."
      ]
    }
  ],
  "disagreement_and_conviction_telemetry": {
    "intrinsic_artistry_composite": 9.05,
    "practical_booking_fit_composite": 9.10,
    "peak_champion_score": 9.30,
    "critic_score_std_dev": 1.11,
    "archetype_classification": "PRE_VIRAL_SCENE_STAR",
    "viral_mirage_risk": "low",
    "consensus_mediocrity_flag": false,
    "preserved_dissent_summary": "Artistry and Booking agents rate 9.1–9.3 on vocal rarity and plug-and-play NYC draw; Red-Team Skeptic flags shallow released catalog (2 songs) requiring set-length verification before slotting as closer vs. middle feature."
  },
  "bill_and_roster_pairing": {
    "recommended_slot_position": "middle_spotlight_25min",
    "complementary_sonic_bill_archetypes": [
      "Pair between a warm indie-folk opener and a 4-piece rhythmic alt-soul closer to maximize dynamic contrast."
    ],
    "downstream_agency_sync_upside": "Prime candidate for boutique booking intro (Ground Control / High Road / TBA tier) within 6–9 months post-EP, plus immediate one-stop indie film sync."
  },
  "producer_synthesis_action": {
    "decision_status": "callback_recommended_pending_human_review",
    "autonomous_outreach_sent": false,
    "suggested_paid_honorarium_usd": 300,
    "draft_invitation_artifact": {
      "status": "pending_human_review",
      "subject": "Paid Showcase Invitation — First Listen NYC (25-Min Featured Vocalist Slot)",
      "personalized_evidence_hook": "Heard your live upstairs set at Pianos—specifically the radiator/burnt-cinnamon verse and the way the room went quiet on that pre-chorus phrasing.",
      "open_confirmations_requested": [
        "Availability for upcoming First Listen NYC date window",
        "Confirmation of 20–25 min original set readiness & 2-channel tech setup",
        "Confirmation of $300 guaranteed showcase honorarium + 100% artist merch retention"
      ]
    }
  }
}
```

---

## Part 4: Extensibility Blueprint (Beyond Music Vocalists to Multi-Vertical Talent Agencies)

Because CAA, WME, UTA, and Wasserman operate across music, comedy, creators, acting, and live speaking, designing Simon's 4-stage pipeline with **domain-core invariants + pluggable vertical adapters** ensures immediate extensibility:

| Pipeline Layer | Universal Talent Agency Core (Invariant) | Music / Vocalist Adapter (*First Listen NYC*) | Stand-Up Comedy / Live Creator Adapter (Future) |
| :--- | :--- | :--- | :--- |
| **Stage 1: Identity & Rep Graph** | Stage/legal entity, home market, visa/age gates, territory representation stack (Mgr / Agent / Publicist / Legal), white-space flags | ISNI, IPI/CAE, PRO (`ASCAP/BMI`), Label/Publisher/Distributor | SAG-AFTRA / WGA status, literary vs. touring agent, podcast network |
| **Stage 2: Multimodal Digestion** | Native audio/video analysis of raw craft, live-vs-edited delta, synthetic/AI check, room-audio crowd reaction | Timbre, pitch center, Melodyne/playback audit, pocket, hook density | Joke-per-minute (`laughs/min`), crowd-work agility vs. scripted bit, timing pauses, room laugh-decay dB |
| **Stage 3: Scout Enrichment** | Conversion ratios over vanity reach, geographic trigger cities, hard-ticket room ladder, comment pull forensics | Save/skip rate, Pollstar club caps, GBOR/NBOR, one-stop sync, producer credits | Club cellars (`Comedy Cellar, Bell House, Union Hall`), clip-to-ticket conversion, podcast guest spikes |
| **Stage 4: Taste & Standout** | Blind artistry critic + cultural strategist + booking validator + red-team skeptic + preserved dissent + `pending_human_review` offer | Showcase slot length, shared backline changeover, FFO bill pairing | 10-min club spot vs. 45-min feature readiness, clean vs. blue room fit |

---

## Sources & Industry Reference Index

1. **Booking Agencies & Live Deal Mechanics**:
   - *Pollstar / Pollstar Boxoffice* (Hard-ticket reporting, GBOR/NBOR settlements, artist average gross/capacity benchmarks).
   - *Prism.fm, Gigwell, Overture, Master Tour* (Booking CRM schemas: flat guarantees, versus deals, plus deals, door splits, split-point calculations, radius clauses, stage plots, input lists, touring party daily nuts).
   - *ROSTR* (Industry representation directory taxonomy: territorial booking splits across WME, CAA, UTA, Wasserman Music, Ground Control Touring, High Road Touring; management, label, distro, and publishing relationships).
   - *Mercury East Presents / Bowery Presents & NYC Indie Venue Ecosystem* (NYC room-capacity ladder: Sofar Sounds / Arlene's Grocery / Pianos → Mercury Lounge / Baby's All Right → Bowery Ballroom / Music Hall of Williamsburg).
2. **A&R Telemetry, Credits & Rights Databases**:
   - *Chartmetric, Soundcharts, Sodatone (WMG), Luminate, Viberate* (Spotify Popularity Index 0–100 algorithmic thresholds, Save Rate 3–8%+ benchmarks, Skip Rate <25% & Completion Rate >50% retention diagnostics, Follower-to-Monthly-Listener ratio, Streams-per-Listener, Geographic Trigger Cities).
   - *DISCO.ac, CISAC, ASCAP/BMI Songview, ISO ISNI* (One-stop sync clearance dossiers, master/publishing split verification, ISRC, ISWC, CAE/IPI, stems/instrumental delivery).
   - *Jaxsta, Muso.AI, MusicBrainz* (Official studio, producer, engineer, songwriter, and session musician credit graphs).
3. **AI Authenticity & Modern A&R Thesis Literature (2025–2026)**:
   - *Deezer AI Detection & IRCAM Amplify / Pex / BeatDapp / HAIM Benchmark* (Spectral/neural decoder artifact detection for Suno/Udio synthetic uploads, hybrid human-AI attribution, streaming fraud filtering).
   - *OnesToWatch, Chartlex, Music Business Worldwide, Berklee A&R Studies* (The "Viral Meme vs. Career Artist" disconnect, slow-burn live worldbuilding exemplified by Chappell Roan / Mk.gee / Dijon, studio-to-stage Melodyne/playback hazards, and pre-DSP scene discovery).
