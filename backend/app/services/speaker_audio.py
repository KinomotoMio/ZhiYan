from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.slidev_sidecar import (
    build_slidev_persistence_payload,
    normalize_slidev_sidecar,
    validate_slidev_slide_id,
)
from app.utils.security import get_safe_httpx_client


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def compute_speaker_notes_hash(notes: str) -> str:
    return hashlib.sha256(notes.encode("utf-8")).hexdigest()


def build_speaker_audio_playback_path(session_id: str, slide_id: str) -> str:
    return f"/api/v1/sessions/{session_id}/slides/{slide_id}/speaker-audio"


def _tts_root() -> Path:
    return (settings.project_root / "data" / "tts").resolve()


def _resolve_storage_path(
    *,
    workspace_id: str,
    session_id: str,
    slide_id: str,
    text_hash: str,
) -> Path:
    return (_tts_root() / workspace_id / session_id / slide_id / f"{text_hash}.mp3").resolve()


def _sanitize_existing_storage_path(storage_path: str) -> Path:
    path = Path(storage_path).resolve()
    root = _tts_root()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("speakerAudio.storagePath 超出允许目录") from exc
    return path


async def _request_minimax_tts(notes: str) -> bytes:
    if settings.tts_provider.strip().lower() != "minimax":
        raise ValueError(f"暂不支持的 TTS provider: {settings.tts_provider}")
    if not settings.tts_api_key.strip():
        raise ValueError("未配置 TTS API Key，无法生成录音")

    request_url = f"{settings.tts_base_url.rstrip('/')}/v1/t2a_v2"
    payload = {
        "model": settings.tts_model,
        "text": notes[:10000],
        "stream": False,
        "voice_setting": {
            "voice_id": settings.tts_voice_id,
            "speed": 1,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "subtitle_enable": False,
        "output_format": "hex",
    }

    try:
        async with get_safe_httpx_client(
            timeout=45,
            url_policy="https_domain_only",
        ) as client:
            resp = await client.post(
                request_url,
                headers={
                    "Authorization": f"Bearer {settings.tts_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise TimeoutError("TTS 服务超时") from exc

    if resp.status_code != 200:
        raise ValueError(f"TTS 服务返回错误: HTTP {resp.status_code}")

    body = resp.json()
    base_resp = body.get("base_resp") if isinstance(body, dict) else None
    status_code_raw = base_resp.get("status_code") if isinstance(base_resp, dict) else None
    try:
        status_code = int(status_code_raw) if status_code_raw is not None else None
    except (TypeError, ValueError):
        status_code = None
    if not isinstance(base_resp, dict) or status_code != 0:
        raise ValueError(
            f"TTS 服务返回业务错误: {base_resp.get('status_msg') if isinstance(base_resp, dict) else 'unknown'}"
        )
    data = body.get("data") if isinstance(body, dict) else None
    audio_hex = data.get("audio") if isinstance(data, dict) else None
    if not isinstance(audio_hex, str) or not audio_hex.strip():
        raise ValueError("TTS 返回内容缺少音频数据")
    try:
        return bytes.fromhex(audio_hex)
    except ValueError as exc:
        raise ValueError("TTS 返回的音频数据格式无效") from exc


async def ensure_speaker_audio_for_slide(
    *,
    workspace_id: str,
    session_id: str,
    slide_id: str,
) -> tuple[dict, dict]:
    from app.services.sessions import session_store

    latest = await session_store.get_latest_presentation(workspace_id, session_id)
    if not latest:
        raise ValueError("当前会话暂无演示稿")
    output_mode = str(latest.get("output_mode") or "").strip()
    presentation = deepcopy(latest.get("presentation")) if isinstance(latest.get("presentation"), dict) else None
    slidev_meta: dict | None = None
    centi_artifact: dict | None = None

    if output_mode == "slidev":
        latest_slidev = await session_store.get_latest_slidev_deck(workspace_id, session_id)
        if latest_slidev is None:
            raise ValueError("当前会话暂无 Slidev 演示稿")
        _markdown, slidev_meta = latest_slidev
        if validate_slidev_slide_id(slidev_meta, slide_id) is None:
            raise ValueError("指定 slide 不存在")
        sidecar = normalize_slidev_sidecar(await session_store.get_latest_slidev_sidecar(workspace_id, session_id))
        notes = str(sidecar["speaker_notes"].get(slide_id) or "").strip()
        if not notes:
            raise ValueError("当前页还没有演讲者注解")
        speaker_audio = sidecar["speaker_audio"].get(slide_id)
    elif output_mode == "html":
        centi = await session_store.get_latest_centi_deck(workspace_id, session_id)
        if centi is None:
            raise ValueError("当前会话暂无 centi-deck 演示稿")
        centi_artifact, _centi_render = centi
        target_slide = next(
            (
                slide
                for slide in (centi_artifact.get("slides") or [])
                if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id
            ),
            None,
        )
        if target_slide is None:
            raise ValueError("指定 slide 不存在")
        # Prefer explicit notes field; fall back to plainText
        notes = str(target_slide.get("notes") or target_slide.get("plainText") or "").strip()
        if not notes:
            raise ValueError("当前页还没有演讲者注解")
        speaker_audio = target_slide.get("speakerAudio") if isinstance(target_slide.get("speakerAudio"), dict) else None
    else:
        if not isinstance(presentation, dict):
            raise ValueError("当前会话暂无演示稿")
        slides = list(presentation.get("slides") or [])
        target_slide = next(
            (
                slide
                for slide in slides
                if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id
            ),
            None,
        )
        if target_slide is None:
            raise ValueError("指定 slide 不存在")

        notes = str(target_slide.get("speakerNotes") or "").strip()
        if not notes:
            raise ValueError("当前页还没有演讲者注解")
        speaker_audio = target_slide.get("speakerAudio")

    text_hash = compute_speaker_notes_hash(notes)
    storage_path = _resolve_storage_path(
        workspace_id=workspace_id,
        session_id=session_id,
        slide_id=slide_id,
        text_hash=text_hash,
    )
    if isinstance(speaker_audio, dict):
        existing_hash = str(speaker_audio.get("textHash") or "").strip()
        existing_path = str(speaker_audio.get("storagePath") or "").strip()
        if existing_hash == text_hash and existing_path:
            path = _sanitize_existing_storage_path(existing_path)
            if path.exists() and path.is_file():
                return speaker_audio, presentation or {}

    if not storage_path.exists() or not storage_path.is_file():
        audio_bytes = await _request_minimax_tts(notes)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(audio_bytes)

    next_audio = {
        "provider": settings.tts_provider,
        "model": settings.tts_model,
        "voiceId": settings.tts_voice_id,
        "textHash": text_hash,
        "storagePath": str(storage_path),
        "mimeType": "audio/mpeg",
        "generatedAt": _utc_now_iso(),
    }
    if output_mode == "html":
        if centi_artifact is None:
            raise ValueError("当前会话暂无 centi-deck 演示稿")
        centi = await session_store.get_latest_centi_deck(workspace_id, session_id)
        if centi is None:
            raise ValueError("当前会话暂无 centi-deck 演示稿")
        stored_artifact, stored_render = centi
        updated_artifact = deepcopy(stored_artifact)
        updated_render = deepcopy(stored_render)
        for slide in list(updated_artifact.get("slides") or []):
            if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id:
                slide["speakerAudio"] = next_audio
                break
        for slide in list(updated_render.get("slides") or []):
            if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id:
                slide["speakerAudio"] = next_audio
                break
        await session_store.set_latest_centi_deck(
            session_id=session_id,
            artifact=updated_artifact,
            render=updated_render,
        )
    elif output_mode == "slidev":
        sidecar = normalize_slidev_sidecar(await session_store.get_latest_slidev_sidecar(workspace_id, session_id))
        sidecar["speaker_audio"][slide_id] = next_audio
        payload = build_slidev_persistence_payload(
            latest,
            title=str((slidev_meta or {}).get("title") or "新演示文稿"),
        )
        await session_store.save_presentation(
            session_id=session_id,
            payload=payload,
            is_snapshot=False,
            snapshot_label=None,
            output_mode="slidev",
            slidev_sidecar=sidecar,
        )
    else:
        if not isinstance(presentation, dict):
            raise ValueError("当前会话暂无演示稿")
        target_slide = next(
            (
                slide
                for slide in list(presentation.get("slides") or [])
                if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id
            ),
            None,
        )
        if target_slide is None:
            raise ValueError("指定 slide 不存在")
        target_slide["speakerAudio"] = next_audio
        await session_store.save_presentation(
            session_id=session_id,
            payload=presentation,
            is_snapshot=False,
            snapshot_label=None,
        )
    return next_audio, presentation or {}


async def resolve_speaker_audio_path(
    *,
    workspace_id: str,
    session_id: str,
    slide_id: str,
) -> tuple[Path, dict]:
    from app.services.sessions import session_store

    latest = await session_store.get_latest_presentation(workspace_id, session_id)
    if not latest:
        raise ValueError("当前会话暂无演示稿")
    output_mode = str(latest.get("output_mode") or "").strip()
    if output_mode == "slidev":
        latest_slidev = await session_store.get_latest_slidev_deck(workspace_id, session_id)
        if latest_slidev is None:
            raise ValueError("当前会话暂无 Slidev 演示稿")
        _markdown, slidev_meta = latest_slidev
        if validate_slidev_slide_id(slidev_meta, slide_id) is None:
            raise ValueError("指定 slide 不存在")
        sidecar = normalize_slidev_sidecar(await session_store.get_latest_slidev_sidecar(workspace_id, session_id))
        speaker_audio = sidecar["speaker_audio"].get(slide_id)
    elif output_mode == "html":
        centi = await session_store.get_latest_centi_deck(workspace_id, session_id)
        if centi is None:
            raise ValueError("当前会话暂无 centi-deck 演示稿")
        centi_artifact, _centi_render = centi
        target_slide = next(
            (
                slide
                for slide in (centi_artifact.get("slides") or [])
                if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id
            ),
            None,
        )
        if target_slide is None:
            raise ValueError("指定 slide 不存在")
        speaker_audio = target_slide.get("speakerAudio") if isinstance(target_slide.get("speakerAudio"), dict) else None
    else:
        slides = list((latest.get("presentation") or {}).get("slides") or [])
        target_slide = next(
            (
                slide
                for slide in slides
                if isinstance(slide, dict) and str(slide.get("slideId") or "") == slide_id
            ),
            None,
        )
        if target_slide is None:
            raise ValueError("指定 slide 不存在")
        speaker_audio = target_slide.get("speakerAudio")
    if not isinstance(speaker_audio, dict):
        raise ValueError("当前页还没有生成录音")
    storage_path = str(speaker_audio.get("storagePath") or "").strip()
    if not storage_path:
        raise ValueError("录音路径缺失")
    path = _sanitize_existing_storage_path(storage_path)
    if not path.exists() or not path.is_file():
        raise ValueError("录音文件不存在，请重新生成")
    return path, speaker_audio
