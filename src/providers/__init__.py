from src.providers.anthropic_provider import AnthropicProvider
from src.providers.deepseek_provider import DeepSeekProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_provider import OpenAIProvider
from src.providers.openrouter_provider import OpenRouterProvider


def make_provider(
    name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    default_model: str | None = None,
):
    """Tạo adapter provider.

    Mọi tham số đều là `None` = giữ hành vi cũ: adapter tự đọc key từ biến môi trường và model/base
    URL từ `Settings` (hoặc `os.getenv` với OpenRouter).

    Truyền tường minh khi cấu hình đến từ MỘT lượt gọi cụ thể - key riêng của người đang test, hoặc
    model đang được xoay vòng. Không đi qua `os.environ` vì đó là biến toàn process: hai request
    song song sẽ đè lên nhau và request này gọi bằng key/model của request kia.

    `base_url` chỉ có ý nghĩa với các adapter OpenAI-compatible (openai/deepseek/openrouter);
    gemini và anthropic dùng SDK riêng, không có endpoint để đổi.
    """
    if name == "openai":
        return OpenAIProvider(api_key=api_key, base_url=base_url, default_model=default_model)
    if name == "openrouter":
        return OpenRouterProvider(api_key=api_key, base_url=base_url, default_model=default_model)
    if name == "anthropic":
        return AnthropicProvider(api_key=api_key, default_model=default_model)
    if name == "gemini":
        return GeminiProvider(api_key=api_key, default_model=default_model)
    if name == "deepseek":
        return DeepSeekProvider(api_key=api_key, base_url=base_url, default_model=default_model)
    raise ValueError(f"Unknown provider: {name}")
