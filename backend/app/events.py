from __future__ import annotations

import json
from datetime import datetime

from .extensions import db
from .models import SessionEvent


class EventHub:
    def __init__(self, bus):
        self.bus = bus
        self._seq: dict[int, int] = {}

    def _next_seq(self, session_id: int) -> int:
        current = self._seq.get(session_id)
        if current is None:
            last = (
                SessionEvent.query.filter_by(session_id=session_id)
                .order_by(SessionEvent.id.desc())
                .first()
            )
            current = last.id if last else 0
        current += 1
        self._seq[session_id] = current
        return current

    def emit(self, session_id: int, event_type: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        seq = self._next_seq(session_id)
        event = {
            "seq": seq,
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        row = SessionEvent(
            session_id=session_id,
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        db.session.add(row)
        db.session.commit()
        event["id"] = row.id
        event["seq"] = row.id
        self._seq[session_id] = row.id
        self.bus.publish(f"session:{session_id}", event)
        return event
