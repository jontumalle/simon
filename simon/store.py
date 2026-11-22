"""SQLite persistence store for Simon's artist leads, clip evidence, observations, and assessments.

Satisfies Requirement 4 (Artist and evidence records) and the Wispr Flow team design
for persisting query, evidence, and synthesis outputs in a lightweight local database.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from .models import ScoutRun


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "local" / "simon.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scout_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    brief_id TEXT NOT NULL,
    brief_prompt TEXT NOT NULL,
    decision_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artist_leads (
    run_id TEXT NOT NULL,
    lead_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    attribution_status TEXT NOT NULL,
    attribution_notes TEXT NOT NULL,
    source_links_json TEXT NOT NULL,
    PRIMARY KEY (run_id, lead_id)
);

CREATE TABLE IF NOT EXISTS clip_evidence (
    run_id TEXT NOT NULL,
    clip_id TEXT NOT NULL,
    lead_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel TEXT NOT NULL,
    recording_context TEXT NOT NULL,
    recording_context_notes TEXT NOT NULL,
    evaluated_model TEXT NOT NULL,
    interaction_id TEXT,
    PRIMARY KEY (run_id, clip_id)
);

CREATE TABLE IF NOT EXISTS clip_observations (
    run_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    clip_id TEXT NOT NULL,
    lead_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    play_url TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    seconds INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    musical_choice TEXT NOT NULL,
    PRIMARY KEY (run_id, observation_id)
);

CREATE TABLE IF NOT EXISTS artist_assessments (
    run_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    brief_id TEXT NOT NULL,
    lead_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    clip_count INTEGER NOT NULL,
    single_clip_flag INTEGER NOT NULL,
    uncertain_attribution_flag INTEGER NOT NULL,
    shortlisted INTEGER NOT NULL,
    fit_rationale TEXT NOT NULL,
    open_questions_json TEXT NOT NULL,
    source_links_json TEXT NOT NULL,
    PRIMARY KEY (run_id, assessment_id)
);

CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (collection, doc_id)
);
"""


class SimonStore:
    """Normalized SQLite storage for ScoutRun records and evidence queries."""

    backend = "sqlite"

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = str(db_path) if db_path is not None else str(DEFAULT_DB_PATH)
        self._memory_conn: Optional[sqlite3.Connection] = None
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_conn.row_factory = sqlite3.Row
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def save_run(self, run: ScoutRun) -> None:
        payload = run.to_dict()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO scout_runs
                    (run_id, mode, brief_id, brief_prompt, decision_status, created_at, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.mode,
                        run.brief.brief_id,
                        run.brief.prompt,
                        run.decision_status,
                        run.created_at,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                conn.execute("DELETE FROM artist_leads WHERE run_id = ?", (run.run_id,))
                conn.execute("DELETE FROM clip_evidence WHERE run_id = ?", (run.run_id,))
                conn.execute("DELETE FROM clip_observations WHERE run_id = ?", (run.run_id,))
                conn.execute("DELETE FROM artist_assessments WHERE run_id = ?", (run.run_id,))

                for lead in run.artist_leads:
                    conn.execute(
                        """
                        INSERT INTO artist_leads
                        (run_id, lead_id, stage_name, attribution_status, attribution_notes, source_links_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run.run_id,
                            lead.lead_id,
                            lead.stage_name,
                            lead.attribution_status,
                            lead.attribution_notes,
                            json.dumps(lead.source_links, ensure_ascii=False),
                        ),
                    )

                for clip in run.clip_evidence:
                    conn.execute(
                        """
                        INSERT INTO clip_evidence
                        (run_id, clip_id, lead_id, stage_name, source_url, video_id, title, channel,
                         recording_context, recording_context_notes, evaluated_model, interaction_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run.run_id,
                            clip.clip_id,
                            clip.lead_id,
                            clip.stage_name,
                            clip.source_url,
                            clip.video_id,
                            clip.title,
                            clip.channel,
                            clip.recording_context,
                            clip.recording_context_notes,
                            clip.evaluated_model,
                            clip.interaction_id,
                        ),
                    )
                    for obs in clip.observations:
                        conn.execute(
                            """
                            INSERT INTO clip_observations
                            (run_id, observation_id, clip_id, lead_id, source_url, play_url,
                             timestamp, seconds, dimension, musical_choice)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run.run_id,
                                obs.observation_id,
                                clip.clip_id,
                                clip.lead_id,
                                obs.source_url,
                                obs.play_url,
                                obs.timestamp,
                                obs.seconds,
                                obs.dimension,
                                obs.musical_choice,
                            ),
                        )

                for assessment in run.assessments:
                    conn.execute(
                        """
                        INSERT INTO artist_assessments
                        (run_id, assessment_id, brief_id, lead_id, stage_name, clip_count,
                         single_clip_flag, uncertain_attribution_flag, shortlisted, fit_rationale,
                         open_questions_json, source_links_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run.run_id,
                            assessment.assessment_id,
                            assessment.brief_id,
                            assessment.lead_id,
                            assessment.stage_name,
                            assessment.clip_count,
                            int(assessment.single_clip_flag),
                            int(assessment.uncertain_attribution_flag),
                            int(assessment.shortlisted),
                            assessment.fit_rationale,
                            json.dumps(assessment.open_questions, ensure_ascii=False),
                            json.dumps(assessment.source_links, ensure_ascii=False),
                        ),
                    )
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT payload_json FROM scout_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return json.loads(row["payload_json"]) if row else None
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT run_id, mode, brief_id, brief_prompt, decision_status, created_at
                FROM scout_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def get_observations_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT observation_id, clip_id, lead_id, source_url, play_url,
                       timestamp, seconds, dimension, musical_choice
                FROM clip_observations
                WHERE run_id = ?
                ORDER BY clip_id, seconds ASC
                """,
                (run_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def save_document(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(data)
        payload.setdefault("doc_id", doc_id)
        updated_at = datetime.now(timezone.utc).isoformat()
        payload["updated_at"] = updated_at
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO documents (collection, doc_id, updated_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (collection, doc_id, updated_at, json.dumps(payload, ensure_ascii=False)),
                )
        finally:
            if self.db_path != ":memory:":
                conn.close()
        return payload

    def save_documents_batch(
        self, items: List[tuple[str, str, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Save many documents inside a single SQLite transaction."""
        if not items:
            return []
        updated_at = datetime.now(timezone.utc).isoformat()
        saved: List[Dict[str, Any]] = []
        rows_to_insert = []
        for collection, doc_id, data in items:
            payload = dict(data)
            payload.setdefault("doc_id", doc_id)
            payload["updated_at"] = updated_at
            saved.append(payload)
            rows_to_insert.append(
                (collection, doc_id, updated_at, json.dumps(payload, ensure_ascii=False))
            )
        conn = self._connect()
        try:
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO documents (collection, doc_id, updated_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
        finally:
            if self.db_path != ":memory:":
                conn.close()
        return saved

    def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT payload_json FROM documents WHERE collection = ? AND doc_id = ?",
                (collection, doc_id),
            ).fetchone()
            return json.loads(row["payload_json"]) if row else None
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def list_documents(self, collection: str, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT payload_json FROM documents
                WHERE collection = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (collection, limit),
            ).fetchall()
            return [json.loads(row["payload_json"]) for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()


def create_store(
    db_path: Optional[Path | str] = None,
    backend: Optional[str] = None,
) -> Any:
    """Create the active persistence store (`sqlite` locally or `firestore` on Cloud Run)."""
    selected = (backend or os.environ.get("SIMON_STORE_BACKEND") or "sqlite").strip().lower()
    if selected == "firestore":
        from .firestore_store import FirestoreStore

        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID") or None
        database = os.environ.get("FIRESTORE_DATABASE") or "(default)"
        return FirestoreStore(project=project, database=database)
    if selected == "sqlite":
        return SimonStore(db_path=db_path)
    raise ValueError(f"Unsupported SIMON_STORE_BACKEND={selected!r}; expected 'sqlite' or 'firestore'.")
