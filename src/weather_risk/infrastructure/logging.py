import logging

_PACKAGE_LOGGER = "weather_risk"


def configure_logging(level: str) -> None:
    """Send this package's logs to stderr at ``level``, independent of the server's config."""
    logger = logging.getLogger(_PACKAGE_LOGGER)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.propagate = False
