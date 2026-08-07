from src.providers.anthropic_provider import AnthropicProvider
from src.providers.deepseek_provider import DeepSeekProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_provider import OpenAIProvider
from src.providers.openrouter_provider import OpenRouterProvider


def make_provider(name: str):
    if name == "openai":
        return OpenAIProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "gemini":
        return GeminiProvider()
    if name == "deepseek":
        return DeepSeekProvider()
    raise ValueError(f"Unknown provider: {name}")
