"""Typed domain records and validation contracts for Simon's Taste-Brief YouTube Scout MVP.

Follows the three-unit pipeline architecture:
1. Discovery Unit   : TasteBrief -> ArtistLead[]
2. Evaluation Unit  : ArtistLead + YouTube URL -> ClipEvidence (1-2 timestamped observations + recording_context)
3. Synthesis Unit   : TasteBrief + ArtistLead[] + ClipEvidence[] -> ArtistAssessment[] + ShortlistEntry[<=3]
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .youtube import (
    build_embed_url,
    build_play_first_url,
    canonical_watch_url,
    extract_video_id,
    seconds_to_timestamp,
    timestamp_to_seconds,
)

VALID_DIMENSIONS = ("phrasing", "dynamics", "interpretation", "arrangement")
VALID_RECORDING_CONTEXTS = ("live", "studio", "unclear")
VALID_ATTRIBUTION_STATUSES = ("verified", "uncertain")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class TasteBrief:
    brief_id: str
    prompt: str
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(cls, prompt: str, brief_id: Optional[str] = None) -> "TasteBrief":
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise ValueError("Taste brief cannot be empty.")
        return cls(brief_id=brief_id or new_id("brief"), prompt=cleaned)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArtistLead:
    lead_id: str
    stage_name: str
    source_links: List[str]
    attribution_status: str = "verified"  # "verified" | "uncertain"
    attribution_notes: str = ""
    videos: List[Dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stage_name = (self.stage_name or "Unknown Performer").strip()
        canonical_links: List[str] = []
        for link in self.source_links:
            watch = canonical_watch_url(link)
            if watch not in canonical_links:
                canonical_links.append(watch)
        if not canonical_links:
            raise ValueError(f"ArtistLead {self.lead_id!r} requires at least one public YouTube URL.")
        self.source_links = canonical_links
        if self.attribution_status not in VALID_ATTRIBUTION_STATUSES:
            self.attribution_status = "uncertain"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimestampedObservation:
    observation_id: str
    clip_id: str
    source_url: str
    timestamp: str
    seconds: int
    play_url: str
    embed_url: str
    dimension: str  # "phrasing" | "dynamics" | "interpretation" | "arrangement"
    musical_choice: str

    @classmethod
    def create(
        cls,
        clip_id: str,
        source_url: str,
        timestamp: Any,
        dimension: str,
        musical_choice: str,
        observation_id: Optional[str] = None,
    ) -> "TimestampedObservation":
        watch_url = canonical_watch_url(source_url)
        secs = timestamp_to_seconds(timestamp)
        ts_str = seconds_to_timestamp(secs)
        dim = (dimension or "phrasing").strip().lower()
        if dim not in VALID_DIMENSIONS:
            dim = "interpretation"
        choice = (musical_choice or "").strip()
        if not choice:
            raise ValueError("TimestampedObservation requires a non-empty musical_choice.")
        return cls(
            observation_id=observation_id or new_id("obs"),
            clip_id=clip_id,
            source_url=watch_url,
            timestamp=ts_str,
            seconds=secs,
            play_url=build_play_first_url(watch_url, secs),
            embed_url=build_embed_url(watch_url, secs, autoplay=False),
            dimension=dim,
            musical_choice=choice,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClipEvidence:
    clip_id: str
    lead_id: str
    stage_name: str
    source_url: str
    video_id: str
    title: str
    channel: str
    recording_context: str  # "live" | "studio" | "unclear"
    recording_context_notes: str
    observations: List[TimestampedObservation]
    evaluated_model: str = "gemini-4-hydrogen"
    interaction_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.source_url = canonical_watch_url(self.source_url)
        self.video_id = extract_video_id(self.source_url) or self.video_id
        ctx = (self.recording_context or "unclear").strip().lower()
        self.recording_context = ctx if ctx in VALID_RECORDING_CONTEXTS else "unclear"
        if not (1 <= len(self.observations) <= 2):
            raise ValueError(
                f"ClipEvidence {self.clip_id!r} must carry 1 or 2 timestamped observations (got {len(self.observations)})."
            )
        # Enforce Requirement 4: keep the original source_url on every observation
        for obs in self.observations:
            obs.source_url = self.source_url
            obs.play_url = build_play_first_url(self.source_url, obs.seconds)
            obs.embed_url = build_embed_url(self.source_url, obs.seconds, autoplay=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "lead_id": self.lead_id,
            "stage_name": self.stage_name,
            "source_url": self.source_url,
            "video_id": self.video_id,
            "title": self.title,
            "channel": self.channel,
            "recording_context": self.recording_context,
            "recording_context_notes": self.recording_context_notes,
            "observations": [obs.to_dict() for obs in self.observations],
            "evaluated_model": self.evaluated_model,
            "interaction_id": self.interaction_id,
        }


@dataclass
class ArtistAssessment:
    assessment_id: str
    brief_id: str
    lead_id: str
    stage_name: str
    source_links: List[str]
    clip_count: int
    single_clip_flag: bool
    uncertain_attribution_flag: bool
    fit_rationale: str
    open_questions: List[str]
    shortlisted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShortlistEntry:
    rank: int
    lead_id: str
    stage_name: str
    source_url: str
    play_first_url: str
    play_first_embed_url: str
    play_first_timestamp: str
    play_first_seconds: int
    play_first_clip_title: str
    why_it_fits: str
    what_to_hear_next: str
    listen_next_url: Optional[str]
    single_clip_flag: bool
    uncertain_attribution_flag: bool
    attribution_notes: str
    recording_context: str
    open_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TraceStep:
    step_id: str
    stage: str  # "discovery" | "evaluation" | "second_take_discovery" | "synthesis"
    actor: str
    status: str
    summary: str
    interaction_id: Optional[str] = None
    duration_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScoutRun:
    run_id: str
    mode: str  # "live" | "verified_demo"
    brief: TasteBrief
    artist_leads: List[ArtistLead]
    clip_evidence: List[ClipEvidence]
    assessments: List[ArtistAssessment]
    shortlist: List[ShortlistEntry]
    trace: List[TraceStep]
    decision_status: str = "pending_human_verification"
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if len(self.shortlist) > 3:
            raise ValueError("Listening shortlist may return at most 3 singers.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "brief": self.brief.to_dict(),
            "artist_leads": [lead.to_dict() for lead in self.artist_leads],
            "clip_evidence": [clip.to_dict() for clip in self.clip_evidence],
            "assessments": [assessment.to_dict() for assessment in self.assessments],
            "shortlist": [item.to_dict() for item in self.shortlist],
            "trace": [step.to_dict() for step in self.trace],
            "decision_status": self.decision_status,
            "created_at": self.created_at,
        }
