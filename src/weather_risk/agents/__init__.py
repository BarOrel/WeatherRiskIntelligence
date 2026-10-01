"""Agent layer: an LLM-driven driving adapter (like the HTTP API) over application services.

Depends on application/domain and on its own ports (LLM, conversation memory). Never on
infrastructure, presentation or vendor SDKs. The LLM decides WHAT to call; application and
domain code decide HOW, and remain the only source of numbers.
"""
