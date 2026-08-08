from src.providers.anthropic_provider import AnthropicProvider
from src.providers.deepseek_provider import DeepSeekProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_provider import OpenAIProvider
from src.providers.openrouter_provider import OpenRouterProvider


def make_provider(name: str, *, api_key: str | None = None):
    """Tạo adapter provider.

    `api_key=None` giữ nguyên hành vi cũ: adapter tự đọc key từ biến môi trường tương ứng.
    Truyền key tường minh khi key đến từ request (mỗi người test dùng key riêng) - không đi qua
    os.environ vì đó là biến toàn process, hai request song song sẽ đè key lên nhau.
    """
    if name == "openai":
        return OpenAIProvider(api_key=api_key)
    if name == "openrouter":
        return OpenRouterProvider(api_key=api_key)
    if name == "anthropic":
        return AnthropicProvider(api_key=api_key)
    if name == "gemini":
        return GeminiProvider(api_key=api_key)
    if name == "deepseek":
        return DeepSeekProvider(api_key=api_key)
    raise ValueError(f"Unknown provider: {name}")
