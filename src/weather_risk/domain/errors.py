class DomainError(Exception):
    """Base class for all domain errors."""


class DomainValidationError(DomainError, ValueError):
    """Raised when a domain object would be created in an invalid state."""
