from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.business.passenger_service import PassengerService

from .dependencies import get_passenger_service
from .schemas import LineDetailOut, LiveBusOut, LineSummaryOut, ReportIn, ReportOut, StopDetailOut, StopOut

router = APIRouter(prefix="/api", tags=["passenger"])
Service = Annotated[PassengerService, Depends(get_passenger_service)]


@router.get("/lines", response_model=list[LineSummaryOut], summary="Lines with their current density")
def list_lines(service: Service, q: str | None = Query(None, description="Line number or terminal name")):
    return [LineSummaryOut.of_summary(s) for s in service.list_lines(q)]


@router.get("/lines/{line_id}", response_model=LineDetailOut, summary="Stops and road geometry of a line")
def get_line(line_id: int, service: Service):
    return LineDetailOut.of(service.line_detail(line_id))


@router.get("/lines/{line_id}/buses", response_model=list[LiveBusOut], summary="Live buses on a line")
def get_line_buses(line_id: int, service: Service):
    return [LiveBusOut.of(b) for b in service.line_buses(line_id)]


@router.get("/stops", response_model=list[StopOut], summary="Search stops")
def search_stops(service: Service, q: str | None = None, limit: int = Query(50, ge=1, le=500)):
    return [StopOut.of(s) for s in service.search_stops(q, limit)]


@router.get("/stops/{stop_id}", response_model=StopDetailOut, summary="Stop with serving lines and upcoming arrivals (ETA)")
def get_stop(stop_id: int, service: Service):
    return StopDetailOut.of(service.stop_detail(stop_id))


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_201_CREATED,
             summary="Passenger crowding report")
def submit_report(body: ReportIn, service: Service):
    return ReportOut.of(service.submit_report(body.line_id, body.level, body.stop_id, body.bus_id))
