"""Firestore native JSON persistence store for Simon on Google Cloud Run.

Implements the same interface as `SimonStore` (SQLite) plus native JSON document
storage (`save_document`, `get_document`, `list_documents`) so runs, fleet
dispatches, and agent dossiers survive Cloud Run redeploys.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import ScoutRun


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FirestoreStore:
    """Google Cloud Firestore persistence backend for Simon."""

    backend = "firestore"

    def __init__(
        self,
        project: Optional[str] = None,
        database: str = "(default)",
        client: Any = None,
    ):
        self.project = project
        self.database = database
        if client is not None:
            self._client = client
        else:
            try:
                from google.cloud import firestore  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "Firestore backend requires `google-cloud-firestore`. "
                    "Install it with `pip install google-cloud-firestore`."
                ) from exc
            self._client = firestore.Client(project=project or None, database=database)

    # ------------------------------------------------------------------
    # Native JSON Document API (fleet runs, dossiers, agent outputs)
    # ------------------------------------------------------------------
    def save_document(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(data)
        payload.setdefault("doc_id", doc_id)
        payload["updated_at"] = _utc_now_iso()
        self._client.collection(collection).document(doc_id).set(payload)
        return payload

    def save_documents_batch(
        self, items: List[tuple[str, str, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Commit up to 400 documents per Firestore WriteBatch for sub-second fleet persistence."""
        if not items:
            return []
        now = _utc_now_iso()
        saved: List[Dict[str, Any]] = []
        chunk_size = 400
        for start in range(0, len(items), chunk_size):
            batch = self._client.batch()
            for collection, doc_id, data in items[start : start + chunk_size]:
                payload = dict(data)
                payload.setdefault("doc_id", doc_id)
                payload["updated_at"] = now
                ref = self._client.collection(collection).document(doc_id)
                batch.set(ref, payload)
                saved.append(payload)
            batch.commit()
        return saved

    def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        snap = self._client.collection(collection).document(doc_id).get()
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict()
        return dict(data) if isinstance(data, dict) else None

    def list_documents(self, collection: str, limit: int = 20) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for snap in self._client.collection(collection).stream():
            data = snap.to_dict()
            if isinstance(data, dict):
                docs.append(dict(data))
        docs.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return docs[:limit]

    # ------------------------------------------------------------------
    # ScoutRun compatibility API (mirrors SimonStore)
    # ------------------------------------------------------------------
    def save_run(self, run: ScoutRun) -> None:
        payload = run.to_dict()
        doc = {
            "run_id": run.run_id,
            "mode": run.mode,
            "brief_id": run.brief.brief_id,
            "brief_prompt": run.brief.prompt,
            "decision_status": run.decision_status,
            "created_at": run.created_at,
            "payload": payload,
        }
        self._client.collection("scout_runs").document(run.run_id).set(doc)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        doc = self.get_document("scout_runs", run_id)
        if not doc:
            return None
        payload = doc.get("payload")
        return dict(payload) if isinstance(payload, dict) else doc

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for snap in self._client.collection("scout_runs").stream():
            data = snap.to_dict()
            if not isinstance(data, dict):
                continue
            rows.append(
                {
                    "run_id": data.get("run_id"),
                    "mode": data.get("mode"),
                    "brief_id": data.get("brief_id"),
                    "brief_prompt": data.get("brief_prompt"),
                    "decision_status": data.get("decision_status"),
                    "created_at": data.get("created_at"),
                }
            )
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows[:limit]

    def get_observations_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        run_payload = self.get_run(run_id)
        if not run_payload:
            return []
        observations: List[Dict[str, Any]] = []
        for clip in run_payload.get("clip_evidence") or []:
            if not isinstance(clip, dict):
                continue
            clip_id = clip.get("clip_id")
            lead_id = clip.get("lead_id")
            for obs in clip.get("observations") or []:
                if not isinstance(obs, dict):
                    continue
                observations.append(
                    {
                        "observation_id": obs.get("observation_id"),
                        "clip_id": clip_id,
                        "lead_id": lead_id,
                        "source_url": obs.get("source_url"),
                        "play_url": obs.get("play_url"),
                        "timestamp": obs.get("timestamp"),
                        "seconds": int(obs.get("seconds") or 0),
                        "dimension": obs.get("dimension"),
                        "musical_choice": obs.get("musical_choice"),
                    }
                )
        observations.sort(key=lambda item: (str(item.get("clip_id") or ""), int(item.get("seconds") or 0)))
        return observations
