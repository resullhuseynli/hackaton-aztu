from fastapi import Request

from app.business.operator_service import OperatorService
from app.business.passenger_service import PassengerService
from app.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_passenger_service(request: Request) -> PassengerService:
    return get_container(request).passenger


def get_operator_service(request: Request) -> OperatorService:
    return get_container(request).operator
