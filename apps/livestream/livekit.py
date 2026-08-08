import json
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.exceptions import AuthenticationFailed


class LiveKitUnavailable(APIException):
    status_code = 503
    default_code = "LIVE_PROVIDER_UNAVAILABLE"
    default_detail = "The self-hosted live media service is not configured or unavailable."


def _ensure_configured():
    if not all((settings.LIVEKIT_URL, settings.LIVEKIT_API_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)):
        raise LiveKitUnavailable("LiveKit is not configured.")


def create_participant_token(event, user, *, can_publish=False, room_admin=False):
    _ensure_configured()
    from livekit import api

    identity = f"user-{user.pk}"
    display_name = user.get_full_name().strip() or user.username
    grants = api.VideoGrants(
        room_join=True,
        room=event.room_name,
        room_admin=room_admin,
        room_record=room_admin and event.recording_enabled,
        can_subscribe=True,
        can_publish=can_publish,
        can_publish_data=True,
        can_publish_sources=["camera", "microphone", "screen_share", "screen_share_audio"] if can_publish else [],
    )
    return (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(display_name)
        .with_metadata(json.dumps({"user_id": user.pk, "event_id": event.pk, "is_host": room_admin}))
        .with_grants(grants)
        .with_ttl(timedelta(seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS))
        .to_jwt()
    )


async def _start_egress(event):
    from livekit import api

    client = api.LiveKitAPI(
        settings.LIVEKIT_API_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET,
    )
    file_path = f"{settings.LIVEKIT_RECORDING_PATH_PREFIX.strip('/')}/{event.slug}-{event.pk}.mp4"
    request = api.RoomCompositeEgressRequest(
        room_name=event.room_name,
        layout="speaker-dark",
        file=api.EncodedFileOutput(file_type=api.EncodedFileType.MP4, filepath=file_path),
        preset=api.EncodingOptionsPreset.H264_720P_30,
    )
    try:
        result = await client.egress.start_room_composite_egress(request)
        return result, file_path
    finally:
        await client.aclose()


def start_recording(event):
    _ensure_configured()
    if not event.recording_enabled:
        raise LiveKitUnavailable("Recording is disabled for this event.")
    try:
        return async_to_sync(_start_egress)(event)
    except Exception as exc:
        raise LiveKitUnavailable("LiveKit Egress could not start recording.") from exc


async def _stop_egress(egress_id):
    from livekit import api

    client = api.LiveKitAPI(
        settings.LIVEKIT_API_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET,
    )
    try:
        return await client.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
    finally:
        await client.aclose()


def stop_recording(egress_id):
    _ensure_configured()
    try:
        return async_to_sync(_stop_egress)(egress_id)
    except Exception as exc:
        raise LiveKitUnavailable("LiveKit Egress could not stop recording.") from exc


async def _update_participant(event, user, can_publish):
    from livekit import api

    client = api.LiveKitAPI(settings.LIVEKIT_API_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    try:
        return await client.room.update_participant(api.UpdateParticipantRequest(
            room=event.room_name,
            identity=f"user-{user.pk}",
            permission=api.ParticipantPermission(
                can_subscribe=True, can_publish=can_publish, can_publish_data=True,
                can_publish_sources=["camera", "microphone", "screen_share", "screen_share_audio"] if can_publish else [],
            ),
        ))
    finally:
        await client.aclose()


def update_participant_permissions(event, user, can_publish):
    _ensure_configured()
    try:
        return async_to_sync(_update_participant)(event, user, can_publish)
    except Exception as exc:
        raise LiveKitUnavailable("Participant permissions could not be updated.") from exc


async def _remove_participant(event, user):
    from livekit import api

    client = api.LiveKitAPI(settings.LIVEKIT_API_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    try:
        return await client.room.remove_participant(
            api.RoomParticipantIdentity(room=event.room_name, identity=f"user-{user.pk}")
        )
    finally:
        await client.aclose()


def remove_participant(event, user):
    _ensure_configured()
    try:
        return async_to_sync(_remove_participant)(event, user)
    except Exception as exc:
        raise LiveKitUnavailable("Participant could not be removed.") from exc


def receive_webhook(body, authorization):
    _ensure_configured()
    from livekit import api

    verifier = api.TokenVerifier(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    try:
        return api.WebhookReceiver(verifier).receive(body, authorization)
    except Exception as exc:
        raise AuthenticationFailed("Invalid LiveKit webhook signature.") from exc
