# llm_client.py
from .micron_chat_model import MicronChatModel  # 就是我幫你寫的那個 SimpleChatModel 子類
from django.conf import settings

def get_llm() -> MicronChatModel:
    # 讀取 Django settings / 環境變數
    return MicronChatModel(
        token_url="https://apim-opc-prod.micron.com/token",
        generate_url="https://apim-opc-prod.micron.com/corp/llmservice/generate",
        client_key=settings.MICRON_API_CLIENT_KEY,
        client_secret=settings.MICRON_API_CLIENT_SECRET,
        subscription_key=settings.MICRON_API_SUBSCRIPTION_KEY,
        # 推薦先用「模擬串流」
        use_native_stream=False,             # 日後 Micron 開放原生串流再改 True
        simulate_stream_chunk="token",       # "token" | "sentence" | "line"
        simulate_stream_sleep=0.0,           # 想更像 live 可設 0.01~0.03
        temperature=0.2,
        top_p=0.8,
        max_tokens=2000,
        model="gpt-4.1",
        timeout=60,
        retries=2,
    )
