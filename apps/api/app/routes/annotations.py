import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.routes.tracks import get_track
from app.schemas import AnnotationIn, AnnotationOut, AnnotationUpdate
from app.services import annotations

router = APIRouter(prefix="/tracks/{track_id}/annotations", tags=["annotations"])


@router.get("", response_model=list[AnnotationOut])
def list_annotations(track_id: uuid.UUID, session: Session = Depends(get_session)):
    get_track(session, track_id)
    return annotations.of(session, track_id)


@router.post("", response_model=list[AnnotationOut], status_code=201)
def create_annotation(track_id: uuid.UUID, body: AnnotationIn, session: Session = Depends(get_session)):
    annotations.create(session, get_track(session, track_id), body.model_dump())
    session.commit()
    return annotations.of(session, track_id)


@router.patch("/{annotation_id}", response_model=list[AnnotationOut])
def edit_annotation(
    track_id: uuid.UUID,
    annotation_id: uuid.UUID,
    body: AnnotationUpdate,
    session: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    if annotations.update(session, get_track(session, track_id), annotation_id, changes) is None:
        raise HTTPException(404, "Annotation not found")
    session.commit()
    return annotations.of(session, track_id)


@router.delete("/{annotation_id}", response_model=list[AnnotationOut])
def delete_annotation(track_id: uuid.UUID, annotation_id: uuid.UUID, session: Session = Depends(get_session)):
    if not annotations.remove(session, get_track(session, track_id), annotation_id):
        raise HTTPException(404, "Annotation not found")
    session.commit()
    return annotations.of(session, track_id)
