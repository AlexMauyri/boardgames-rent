"""Client-facing order router: place, list, view, cancel."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_client,
    get_event_publisher,
    get_pricing_client,
    get_session,
)
from app.db.models import Client
from app.integrations.grpc.pricing_client import PricingClient
from app.integrations.rabbitmq.publisher import RabbitPublisher
from app.schemas import OrderCreate, OrderDetailRead, OrderRead, PriceQuoteRead
from app.services import orders as orders_service

router = APIRouter()


@router.post(
    "",
    response_model=OrderDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    client: Annotated[Client, Depends(get_current_client)],
    session: Annotated[AsyncSession, Depends(get_session)],
    pricing: Annotated[PricingClient | None, Depends(get_pricing_client)],
    events: Annotated[RabbitPublisher | None, Depends(get_event_publisher)],
) -> OrderDetailRead:
    """Place a new rental order for the current client."""
    return await orders_service.create_order(
        session, client.id, payload, pricing=pricing, events=events,
    )


@router.post("/quote", response_model=PriceQuoteRead)
async def quote_order(
    payload: OrderCreate,
    client: Annotated[Client, Depends(get_current_client)],
    session: Annotated[AsyncSession, Depends(get_session)],
    pricing: Annotated[PricingClient | None, Depends(get_pricing_client)],
) -> PriceQuoteRead:
    """Price a rental without placing it: duration discount and deposit."""
    return await orders_service.quote_order(session, payload, pricing=pricing)


@router.get("", response_model=list[OrderRead])
async def list_orders(
    client: Annotated[Client, Depends(get_current_client)],
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[OrderRead]:
    """List the current client's orders, newest first."""
    return await orders_service.list_client_orders(
        session, client.id, skip=skip, limit=limit,
    )


@router.get("/{order_id}", response_model=OrderDetailRead)
async def get_order(
    order_id: int,
    client: Annotated[Client, Depends(get_current_client)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderDetailRead:
    """Fetch one of the current client's orders with its lines."""
    return await orders_service.get_order(
        session, order_id, client_id=client.id,
    )


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: int,
    client: Annotated[Client, Depends(get_current_client)],
    session: Annotated[AsyncSession, Depends(get_session)],
    events: Annotated[RabbitPublisher | None, Depends(get_event_publisher)],
) -> OrderRead:
    """Cancel one of the current client's orders and release its boxes."""
    return await orders_service.cancel_order(
        session, order_id, client.id, events=events,
    )