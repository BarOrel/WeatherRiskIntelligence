"""Shared application component for the risk use cases (not a use case itself)."""

from weather_risk.application.risk.assessor import HubRiskAssessor, RiskScope

__all__ = ["HubRiskAssessor", "RiskScope"]
