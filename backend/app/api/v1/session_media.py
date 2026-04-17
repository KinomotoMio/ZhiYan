from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.sessions.workspace import get_workspace_id_from_request
from app.services.speaker_audio import (
    build_speaker_audio_playback_path,
    ensure_speaker_audio_for_slide,
    resolve_speaker_audio_path,
)
from app.services.speaker_notes import (
    generate_speaker_notes_for_session,
    save_slidev_speaker_notes_for_slide,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SpeakerNotesGenerateRequest(BaseModel):
    presentation: dict | None = None
    slidev_notes_state: dict[str, str] | None = Field(default=None, alias="slidevNotesState")
    scope: Literal["current", "all"] = "current"
    current_slide_index: int = Field(default=0, alias="currentSlideIndex")

    model_config = {"populate_by_name": True}


class SpeakerNotesGenerateResponse(BaseModel):
    presentation: dict | None = None
    slidev_notes_state: dict[str, str] | None = Field(default=None, alias="slidevNotesState")
    updated_slide_ids: list[str] = Field(alias="updatedSlideIds")
    workspace_root: str = Field(alias="workspaceRoot")

    model_config = {"populate_by_name": True}


class SlideSpeakerNotesWriteRequest(BaseModel):
    speaker_notes: str = Field(alias="speakerNotes")

    model_config = {"populate_by_name": True}


class SlideSpeakerNotesWriteResponse(BaseModel):
    slide_id: str = Field(alias="slideId")
    speaker_notes: str | None = Field(default=None, alias="speakerNotes")
    slidev_notes_state: dict[str, str] | None = Field(default=None, alias="slidevNotesState")

    model_config = {"populate_by_name": True}


class SpeakerAudioEnsureResponse(BaseModel):
    slide_id: str = Field(alias="slideId")
    speaker_audio: dict = Field(alias="speakerAudio")
    playback_path: str = Field(alias="playbackPath")

    model_config = {"populate_by_name": True}


async def _assert_session_access(workspace_id: str, session_id: str) -> None:
    from app.services.sessions import session_store

    try:
        await session_store.get_session(workspace_id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{session_id}/speaker-notes/generate",
    response_model=SpeakerNotesGenerateResponse,
)
async def generate_speaker_notes(
    session_id: str,
    req: SpeakerNotesGenerateRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    await _assert_session_access(workspace_id, session_id)
    try:
        result = await generate_speaker_notes_for_session(
            workspace_id=workspace_id,
            session_id=session_id,
            presentation_payload=req.presentation,
            slidev_notes_state=req.slidev_notes_state,
            scope=req.scope,
            current_slide_index=req.current_slide_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SpeakerNotesGenerateResponse(
        presentation=result.presentation,
        slidevNotesState=result.slidev_notes_state,
        updatedSlideIds=result.updated_slide_ids,
        workspaceRoot=result.workspace_root,
    )


@router.put(
    "/{session_id}/slides/{slide_id}/speaker-notes",
    response_model=SlideSpeakerNotesWriteResponse,
)
async def save_slide_speaker_notes(
    session_id: str,
    slide_id: str,
    req: SlideSpeakerNotesWriteRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    await _assert_session_access(workspace_id, session_id)
    try:
        result = await save_slidev_speaker_notes_for_slide(
            workspace_id=workspace_id,
            session_id=session_id,
            slide_id=slide_id,
            notes=req.speaker_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SlideSpeakerNotesWriteResponse(
        slideId=slide_id,
        speakerNotes=result.get("speaker_notes"),
        slidevNotesState=result.get("slidev_notes_state"),
    )


@router.post(
    "/{session_id}/slides/{slide_id}/speaker-audio",
    response_model=SpeakerAudioEnsureResponse,
)
async def ensure_speaker_audio(
    session_id: str,
    slide_id: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    await _assert_session_access(workspace_id, session_id)
    try:
        speaker_audio, _presentation = await ensure_speaker_audio_for_slide(
            workspace_id=workspace_id,
            session_id=session_id,
            slide_id=slide_id,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SpeakerAudioEnsureResponse(
        slideId=slide_id,
        speakerAudio=speaker_audio,
        playbackPath=build_speaker_audio_playback_path(session_id, slide_id),
    )


@router.get("/{session_id}/slides/{slide_id}/speaker-audio")
async def get_speaker_audio(
    session_id: str,
    slide_id: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    await _assert_session_access(workspace_id, session_id)
    try:
        path, speaker_audio = await resolve_speaker_audio_path(
            workspace_id=workspace_id,
            session_id=session_id,
            slide_id=slide_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path=str(path),
        media_type=str(speaker_audio.get("mimeType") or "audio/mpeg"),
        filename=path.name,
    )
