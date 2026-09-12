"""AZAZEL: the public reasoning entity over SINGULAR's governed core.

The historical ``singular.jarvis`` package remains as an internal compatibility
implementation during the migration. New application code should import AZAZEL
from this module. Provider identity is an implementation detail: Anthropic/Claude
is a model provider, not a separate agent or authority.
"""

from ..jarvis.llm import AnthropicProvider, LLMProvider, LLMProviderError, LLMResponse, LLMUsage
from ..jarvis.runtime import JarvisRuntime, MissionProposal, ProposedAction

AzazelRuntime = JarvisRuntime
AzazelParseError = __import__("singular.jarvis.runtime", fromlist=["JarvisParseError"]).JarvisParseError

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
