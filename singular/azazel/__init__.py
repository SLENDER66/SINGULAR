"""AZAZEL: the public reasoning entity over SINGULAR's governed core.

The historical ``singular.jarvis`` package remains as an internal compatibility
implementation during migration. New application code should import AZAZEL
from this module. Anthropic/Claude is only a model provider, never a separate
agent or authority.
"""

from ..jarvis.llm import AnthropicProvider, LLMProvider, LLMProviderError, LLMResponse, LLMUsage
from ..jarvis.runtime import AzazelParseError, AzazelRuntime, MissionProposal, ProposedAction

__all__ = [
    "AnthropicProvider",
    "AzazelParseError",
    "AzazelRuntime",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "LLMUsage",
    "MissionProposal",
    "ProposedAction",
]
