class DomainError(Exception):
    """Base class for application-level (non-HTTP) domain errors."""


class InvalidTransitionError(DomainError):
    def __init__(self, entity: str, from_state: str, to_state: str):
        self.entity = entity
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"{entity}: invalid transition {from_state} -> {to_state}")


class ConfigValidationError(DomainError):
    pass


class ConfigVersionError(DomainError):
    pass


class NotFoundError(DomainError):
    def __init__(self, entity: str, entity_id: str):
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} not found: {entity_id}")


class IngestionError(DomainError):
    pass
