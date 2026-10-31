from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.business.operator_service import OperatorService
from app.domain.enums import AlertStatus, DensityLevel

from .dependencies import get_container, get_operator_service
from .schemas import (AlertOut, DensityHistoryOut, DensityPointOut, DispatchIn, DispatchOut, FleetBusOut,
                      LineDensityOut, OverviewOut, SimulationOut, SurgeOut)

router = APIRouter(prefix="/api/operator", tags=["operator"])
demo_router = APIRouter(prefix="/api/demo", tags=["demo"])
Service = Annotated[OperatorService, Depends(get_operator_service)]


@router.get("/overview", response_model=OverviewOut, summary="Network-wide KPIs")
def overview(service: Service):
    return OverviewOut.of(service.overview())


@router.get("/density", response_model=list[LineDensityOut], summary="Density per line, most crowded first")
def density(service: Service, level: DensityLevel | None = None):
    return [LineDensityOut.of(d) for d in service.density(level)]


@router.get("/buses", response_model=list[FleetBusOut], summary="All buses with position and load (density map)")
def fleet(service: Service):
    return [FleetBusOut.of(bus, number) for bus, number in service.fleet()]


@router.get("/density/{line_id}/history", response_model=DensityHistoryOut, summary="Density of a line over time")
def density_history(line_id: int, service: Service, minutes: int = Query(60, ge=5, le=180)):
    line, points = service.history(line_id, minutes)
    return DensityHistoryOut(line_id=line.id, line_number=line.number, points=[DensityPointOut.of(p) for p in points])


@router.get("/alerts", response_model=list[AlertOut], summary="Anomaly alerts")
def alerts(service: Service, status: AlertStatus | None = None, limit: int = Query(100, ge=1, le=500)):
    return [AlertOut.of(a) for a in service.alerts(status, limit)]


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut, summary="Close an alert without action")
def resolve_alert(alert_id: int, service: Service):
    return AlertOut.of(service.resolve(alert_id))


@router.post("/alerts/{alert_id}/dispatch", response_model=DispatchOut,
             summary="Move buses from the donor line to the overcrowded line and close the alert")
def dispatch(alert_id: int, service: Service, body: DispatchIn | None = None):
    body = body or DispatchIn()
    return DispatchOut.of(service.dispatch(alert_id, body.donor_line_id, body.bus_count))


@demo_router.get("/simulation", response_model=SimulationOut, summary="Simulated clock")
def simulation(container=Depends(get_container)):
    return SimulationOut(clock=container.clock.now(), speed=container.clock.speed,
                         tick_seconds=container.settings.tick_seconds)


@demo_router.post("/surge/{line_id}", response_model=SurgeOut, summary="Demo: make a line overcrowded")
def surge(line_id: int, service: Service):
    line = service.surge(line_id)
    return SurgeOut(line_id=line.id, line_number=line.number,
                    message=f"Xətt {line.number} süni şəkildə sıxlaşdırıldı (30 simulyasiya dəqiqəsi).")
