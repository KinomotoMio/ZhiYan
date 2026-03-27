from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import settings
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
    if not isinstance(base_resp, dict) or int(base_resp.get("status_code") or -1) != 0:
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
    presentation = deepcopy(latest["presentation"])
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

    text_hash = compute_speaker_notes_hash(notes)
    storage_path = _resolve_storage_path(
        workspace_id=workspace_id,
        session_id=session_id,
        slide_id=slide_id,
        text_hash=text_hash,
    )
    speaker_audio = target_slide.get("speakerAudio")
    if isinstance(speaker_audio, dict):
        existing_hash = str(speaker_audio.get("textHash") or "").strip()
        existing_path = str(speaker_audio.get("storagePath") or "").strip()
        if existing_hash == text_hash and existing_path:
            path = _sanitize_existing_storage_path(existing_path)
            if path.exists() and path.is_file():
                return speaker_audio, presentation

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
    target_slide["speakerAudio"] = next_audio
    await session_store.save_presentation(
        session_id=session_id,
        payload=presentation,
        is_snapshot=False,
        snapshot_label=None,
    )
    return next_audio, presentation


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
