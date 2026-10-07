"""Service-layer exception vocabulary."""


class NotFoundError(Exception):
    """A requested entity does not exist.

    Attributes:
        entity: Name of the entity type that was looked up.
        id: The identifier that had no match.
    """

    def __init__(self, entity: str, id: int | str) -> None:
        """Initialise the error with the entity name and missing id.

        Args:
            entity: Name of the entity type, e.g. "Client".
            id: The identifier that did not match any row.
        """
        self.entity = entity
        self.id = id
        super().__init__(f"{entity} {id} not found")


class ConflictError(Exception):
    """An entity with the given identifier already exists.

    Attributes:
        entity: Name of the entity type that collided.
        identifier: The natural key value that is already taken.
    """

    def __init__(self, entity: str, identifier: str | int) -> None:
        """Initialise the error with the entity name and colliding identifier.

        Args:
            entity: Name of the entity type, e.g. "Category".
            identifier: The natural key value that already exists.
        """
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} with {identifier!r} already exists")

class NotAvailableError(Exception):
    """The requested games cannot be supplied from the current stock.

    Attributes:
        game_ids: Catalog games that could not be covered, sorted.
        reason: Human-readable explanation.
    """

    def __init__(self, game_ids: list[int], reason: str | None = None) -> None:
        """Initialise the error with the uncovered games.

        Args:
            game_ids: Catalog games that could not be covered.
            reason: Explanation; defaults to a generic stock message.
        """
        self.game_ids = sorted(game_ids)
        self.reason = reason or "no free copies"
        super().__init__(f"Games {self.game_ids} not available: {self.reason}")


class InvalidTransitionError(Exception):
    """An entity is in a state that does not allow the requested action.

    Attributes:
        entity: Name of the entity type, e.g. "Order".
        id: Identifier of the entity.
        current: The status the entity is in.
        action: The action that was refused.
    """

    def __init__(
        self,
        entity: str,
        id: int | str,
        current: str,
        action: str,
    ) -> None:
        """Initialise the error with the refused action and current status.

        Args:
            entity: Name of the entity type.
            id: Identifier of the entity.
            current: The status the entity is in.
            action: The action that was refused.
        """
        self.entity = entity
        self.id = id
        self.current = current
        self.action = action
        super().__init__(
            f"Cannot {action} {entity} {id}: status is {current}"
        )


class ForbiddenError(Exception):
    """The acting user is not allowed to perform the action.

    Attributes:
        reason: Human-readable explanation.
    """

    def __init__(self, reason: str) -> None:
        """Initialise the error with the reason.

        Args:
            reason: Why the action is refused.
        """
        self.reason = reason
        super().__init__(reason)
