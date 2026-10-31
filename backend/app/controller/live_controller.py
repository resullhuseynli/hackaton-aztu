"""WebSocket push of live data.

Connect to /ws/live?line_id=5 for a line's buses, and/or ?operator=true for density and alerts.
Send {"line_id": 7} (or {"line_id": null}) to switch the line without reconnecting.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.container import Container
from app.domain.enums import AlertStatus

from .schemas import AlertOut, LineDensityOut, LiveBusOut, OverviewOut

router = APIRouter(tags=["live"])
PUSH_INTERVAL_SECONDS = 2.0


def build_payload(container: Container, line_id: int | None, operator: bool) -> dict:
    payload: dict = {"clock": container.clock.now().isoformat()}
    if line_id is not None:
        payload["line_id"] = line_id
        payload["buses"] = [LiveBusOut.of(b).model_dump(mode="json") for b in container.passenger.line_buses(line_id)]
    if operator:
        payload["overview"] = OverviewOut.of(container.operator.overview()).model_dump(mode="json")
        payload["density"] = [LineDensityOut.of(d).model_dump(mode="json") for d in container.operator.density()]
        payload["alerts"] = [AlertOut.of(a).model_dump(mode="json")
                             for a in container.operator.alerts(AlertStatus.OPEN)]
    return payload


@router.websocket("/ws/live")
async def live(websocket: WebSocket, line_id: int | None = None, operator: bool = False):
    await websocket.accept()
    container: Container = websocket.app.state.container
    subscription = {"line_id": line_id}

    async def receive():
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and "line_id" in message:
                subscription["line_id"] = message["line_id"]

    receiver = asyncio.create_task(receive())
    try:
        while not receiver.done():
            try:
                payload = await asyncio.to_thread(build_payload, container, subscription["line_id"], operator)
            except Exception as exc:  # e.g. unknown line id
                payload = {"clock": container.clock.now().isoformat(), "error": str(exc)}
            await websocket.send_json(payload)
            await asyncio.wait({receiver}, timeout=PUSH_INTERVAL_SECONDS)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        receiver.cancel()
