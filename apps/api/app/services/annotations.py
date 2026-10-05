"""DJ notes on the timeline (musical positions). Cueflow only: Rekordbox has no place for them."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Annotation, Track


def of(session: Session, track_id: uuid.UUID) -> list[Annotation]:
    query = select(Annotation).where(Annotation.track_id == track_id)
    return list(session.scalars(query.order_by(Annotation.bar, Annotation.beat, Annotation.created_at)))


def create(session: Session, track: Track, fields: dict) -> Annotation:
    annotation = Annotation(track_id=track.id, **fields)
    session.add(annotation)
    session.flush()
    return annotation


def update(session: Session, track: Track, annotation_id: uuid.UUID, changes: dict) -> Annotation | None:
    annotation = session.get(Annotation, annotation_id)
    if annotation is None or annotation.track_id != track.id:
        return None
    for field, value in changes.items():
        setattr(annotation, field, value)
    return annotation


def remove(session: Session, track: Track, annotation_id: uuid.UUID) -> bool:
    annotation = session.get(Annotation, annotation_id)
    if annotation is None or annotation.track_id != track.id:
        return False
    session.delete(annotation)
    return True
