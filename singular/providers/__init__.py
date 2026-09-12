"""Real external-effect providers.

Everything else in this package decides, validates, authorizes and records.
This is where SINGULAR actually touches the world, behind the same boundary as
everything else: a provider is only ever reached through a validated,
attested decision bound to the exact provider artifact.
"""
from .http_effect import HttpEffectProvider, HttpProviderError

__all__ = ["HttpEffectProvider", "HttpProviderError"]
