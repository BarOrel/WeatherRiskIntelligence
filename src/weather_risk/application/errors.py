class ApplicationError(Exception):
    """Base class for application-layer errors."""


class HubNotFoundError(ApplicationError):
    def __init__(self, hub_id: str) -> None:
        super().__init__(f"Hub '{hub_id}' was not found")
        self.hub_id = hub_id


class InvalidDateRangeError(ApplicationError):
    """The requested date range cannot be served (reversed, in the future, or too long)."""


# --- Weather provider ----------------------------------------------------------------------


class WeatherProviderError(ApplicationError):
    """Base class for failures of an external weather provider."""


class WeatherProviderUnavailableError(WeatherProviderError):
    """The provider could not be reached (connection or network failure)."""


class WeatherProviderTimeoutError(WeatherProviderError):
    """The provider did not respond in time."""


class WeatherProviderResponseError(WeatherProviderError):
    """The provider answered with an unexpected HTTP status."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        message = f"Weather provider returned HTTP {status_code}"
        super().__init__(f"{message}: {detail}" if detail else message)
        self.status_code = status_code


class InvalidWeatherDataError(WeatherProviderError):
    """The provider's response was malformed, incomplete or failed validation."""


# --- Hazards -------------------------------------------------------------------------------


class UnsupportedHazardError(ApplicationError):
    """No Hazard is registered for the requested hazard type."""

    def __init__(self, hazard_type: object) -> None:
        super().__init__(f"Hazard type '{hazard_type}' is not supported")
        self.hazard_type = hazard_type


class HazardProviderError(ApplicationError):
    """Base class for failures of an external hazard data provider."""


class HazardProviderUnavailableError(HazardProviderError):
    """The provider could not be reached (connection or network failure)."""


class HazardProviderTimeoutError(HazardProviderError):
    """The provider did not respond in time."""


class HazardProviderResponseError(HazardProviderError):
    """The provider answered with an unexpected HTTP status."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        message = f"Hazard provider returned HTTP {status_code}"
        super().__init__(f"{message}: {detail}" if detail else message)
        self.status_code = status_code


class InvalidHazardDataError(HazardProviderError):
    """The provider's response was malformed, incomplete or failed validation."""


# --- Risk ----------------------------------------------------------------------------------


class InvalidRiskRequestError(ApplicationError):
    """The risk request is invalid (e.g. fewer than two hubs to compare, zero-weight selection)."""
