"""Tests for delivery to live connections."""

from app.auth import Principal
from app.events import Notification, Recipient
from app.hub import ConnectionHub


class _FakeSocket:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.fail = fail

    async def send_json(self, payload):
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(payload)


def _note(recipient: Recipient) -> Notification:
    return Notification(recipient=recipient, payload={"message": "hi"})


async def test_a_specific_user_gets_only_their_notification():
    hub = ConnectionHub()
    mine, other = _FakeSocket(), _FakeSocket()
    hub.add(Principal(1, "CLIENT"), mine)
    hub.add(Principal(2, "CLIENT"), other)

    sent = await hub.deliver(_note(Recipient("CLIENT", 1)))

    assert sent == 1
    assert mine.sent == [{"message": "hi"}]
    assert other.sent == []


async def test_a_role_broadcast_reaches_every_user_of_the_role_only():
    hub = ConnectionHub()
    couriers = [_FakeSocket(), _FakeSocket()]
    client = _FakeSocket()
    hub.add(Principal(4, "COURIER"), couriers[0])
    hub.add(Principal(5, "COURIER"), couriers[1])
    hub.add(Principal(4, "CLIENT"), client)

    sent = await hub.deliver(_note(Recipient("COURIER")))

    assert sent == 2
    assert all(s.sent == [{"message": "hi"}] for s in couriers)
    assert client.sent == []


async def test_every_connection_of_one_user_is_served():
    hub = ConnectionHub()
    phone, laptop = _FakeSocket(), _FakeSocket()
    hub.add(Principal(1, "CLIENT"), phone)
    hub.add(Principal(1, "CLIENT"), laptop)

    assert await hub.deliver(_note(Recipient("CLIENT", 1))) == 2


async def test_delivery_to_nobody_is_not_an_error():
    assert await ConnectionHub().deliver(_note(Recipient("CLIENT", 1))) == 0


async def test_a_dead_connection_is_dropped_and_does_not_block_others():
    hub = ConnectionHub()
    dead, alive = _FakeSocket(fail=True), _FakeSocket()
    hub.add(Principal(4, "COURIER"), dead)
    hub.add(Principal(5, "COURIER"), alive)

    sent = await hub.deliver(_note(Recipient("COURIER")))

    assert sent == 1
    assert hub.count() == 1


async def test_remove_forgets_the_connection_and_is_idempotent():
    hub = ConnectionHub()
    socket = _FakeSocket()
    principal = Principal(1, "CLIENT")
    hub.add(principal, socket)

    hub.remove(principal, socket)
    hub.remove(principal, socket)

    assert hub.count() == 0
