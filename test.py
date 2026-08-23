from anthropic import Anthropic

client = Anthropic(api_key="sk-2c6379c7cf066390c67347e8eacfd41dd73d9e788b27da80ee0f1057e0c0e858", 
                   base_url="https://ttmapi.site")  # Tá»± Ä‘á»c biáº¿n ANTHROPIC_API_KEY

response = client.messages.create(
    model="claude-opus-5",
    max_tokens=1000,
    system="Báº¡n lÃ  má»™t trá»£ lÃ½ AI. HÃ£y tráº£ lá»i báº±ng tiáº¿ng Viá»‡t.",
    messages=[
        {
            "role": "user",
            "content": "Giáº£i thÃ­ch RAG Ä‘Æ¡n giáº£n cho sinh viÃªn."
        }
    ]
)

for block in response.content:
    if block.type == "text":
        print(block.text)

print("Input tokens:", response.usage.input_tokens)
print("Output tokens:", response.usage.output_tokens)

