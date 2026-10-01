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