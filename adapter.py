# custom_llm_adapter.py

import requests
from requests.auth import HTTPBasicAuth
# from django.conf import settings # 註解：在獨立腳本中，我們先不依賴 Django settings

from typing import Any, List, Optional, Dict
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# ==============================================================================
# 您提供的原始服務類別 (為了完整性，將其包含在此)
# ==============================================================================
class MicronLLMService:
    """
    Micron API 客戶端，用於處理外部 API 調用
    """
    def __init__(self):
        self.token_url = "https://apim-opc-prod.micron.com/token"
        self.generate_url = "https://apim-opc-prod.micron.com/corp/llmservice/generate"
        # 為了能在非 Django 環境下執行，我們直接從環境變數讀取
        self.client_key = os.getenv('MICRON_API_CLIENT_KEY', '')
        self.client_secret = os.getenv('MICRON_API_CLIENT_SECRET', '')
        self.subscription_key = os.getenv('MICRON_API_SUBSCRIPTION_KEY', '')
        self._access_token = None

    def generate_access_token(self):
        """生成訪問令牌"""
        auth = HTTPBasicAuth(self.client_key, self.client_secret)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"grant_type": "client_credentials"}
        try:
            response = requests.post(self.token_url, headers=headers, data=data, auth=auth)
            response.raise_for_status() # 如果請求失敗則拋出異常
            print("Access token generated successfully.")
            self._access_token = response.json()["access_token"]
            return self._access_token
        except Exception as e:
            print(f"Error generating access token: {str(e)}")
            return None

    def submit_json_body(self, json_body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提交 JSON 數據到 Micron API"""
        if not self._access_token:
            self.generate_access_token()
        
        if not self._access_token:
            print("No valid access token available")
            return None

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "subscriptionKey": self.subscription_key,
        }
        try:
            response = requests.post(self.generate_url, headers=headers, json=json_body)
            response.raise_for_status()
            print("JSON body submitted successfully.")
            return response.json()
        except requests.exceptions.HTTPError as e:
            # 如果是授權問題 (401)，嘗試重新獲取 token 再試一次
            if e.response.status_code == 401:
                print("Token might have expired. Regenerating and retrying...")
                self.generate_access_token()
                if self._access_token:
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    response = requests.post(self.generate_url, headers=headers, json=json_body)
                    response.raise_for_status()
                    return response.json()
            print(f"Failed to submit JSON body. Response: {e.response.text}")
            return None
        except Exception as e:
            print(f"Error submitting JSON body: {str(e)}")
            return None

    def generate_ai_response(self, sys_prompt, user_prompt, **kwargs):
        """生成 AI 響應的便捷方法"""
        json_body = {
            "sys_prompt": sys_prompt,
            "prompt": user_prompt,
            "model": kwargs.get("model", "gpt-4.1"),
            "temperature": kwargs.get("temperature", 0.2),
            "top_p": kwargs.get("top_p", 0.8),
            "max_tokens": kwargs.get("max_tokens", 2000),
            "stop_words": kwargs.get("stop_words", ["User:", "AI:"])
        }
        return self.submit_json_body(json_body)

# ==============================================================================
# LangChain 轉接頭 (Adapter)
# ==============================================================================
class CustomMicronChat(BaseChatModel):
    """
    一個包裝了 MicronLLMService 的 LangChain 相容聊天模型。
    """
    client: MicronLLMService = MicronLLMService()
    model_name: str = "gpt-4.1"
    temperature: float = 0.2
    top_p: float = 0.8
    max_tokens: int = 2000

    @property
    def _llm_type(self) -> str:
        """返回聊天模型的類型"""
        return "micron-custom-chat"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        LangChain 的核心方法，所有邏輯都在這裡。
        它負責將 LangChain 標準的 message 格式轉換為您 API 所需的格式，
        然後再將 API 的回傳結果轉換回 LangChain 的標準格式。
        """
        # 1. 將 LangChain 的 Message 列表轉換為 sys_prompt 和 user_prompt
        sys_prompt = ""
        user_prompts = []
        for message in messages:
            if isinstance(message, SystemMessage):
                sys_prompt = message.content
            elif isinstance(message, HumanMessage):
                user_prompts.append(message.content)
            elif isinstance(message, AIMessage):
                # 在這個情境下，我們假設對話歷史中的 AI 回應不需要傳遞
                pass
        
        user_prompt = "\n".join(user_prompts)

        # 2. 呼叫您的服務
        response = self.client.generate_ai_response(
            sys_prompt=sys_prompt,
            user_prompt=user_prompt,
            model=self.model_name,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            # 可以將 stop 和其他 kwargs 傳遞下去
            stop_words=stop,
            **kwargs,
        )

        # 3. 處理回傳結果並轉換為 LangChain 格式
        if response is None:
            # 處理 API 調用失敗的情況
            raise IOError("Micron LLM API call failed.")

        # 假設您的 API 回傳格式為 {"generated_text": "..."}
        # 您需要根據實際的回傳格式修改此處的鍵值
        response_text = response.get("generated_text", "") 

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        
        return ChatResult(generations=[generation])

# --- 測試案例 ---
if __name__ == '__main__':
    import os
    
    # 執行前請先設定好您的環境變數
    # export MICRON_API_CLIENT_KEY='your_key'
    # export MICRON_API_CLIENT_SECRET='your_secret'
    # export MICRON_API_SUBSCRIPTION_KEY='your_subscription_key'
    
    print("正在測試自訂的 LangChain LLM 轉接頭...")
    
    # 初始化我們的自訂聊天模型
    custom_llm = CustomMicronChat(model_name="gpt-4.1")
    
    # 建立一個簡單的對話測試
    test_messages = [
        SystemMessage(content="你是一個有用的AI助理。"),
        HumanMessage(content="你好嗎？")
    ]
    
    try:
        result = custom_llm.invoke(test_messages)
        print("\n[直接呼叫測試成功]")
        print(f"AI 回應: {result.content}")
    except Exception as e:
        print(f"\n[直接呼叫測試失敗]: {e}")

