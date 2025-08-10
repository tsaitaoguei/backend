# chatbot/apps.py
# --------------------
# 這是 Django App 的設定檔。我們將在這裡初始化 Agent。

from django.apps import AppConfig

class ChatbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chatbot'
    
    # Agent 的單例將存放在這裡
    agent_executor = None

    def ready(self):
        """
        當 Django 應用程式準備就緒時，這個方法會被自動呼叫。
        這是執行一次性初始化任務的最佳位置。
        """
        # 避免在某些管理命令（如 makemigrations）下重複執行
        import sys
        if 'runserver' not in sys.argv and 'gunicorn' not in sys.argv:
            return

        print("--- [ChatbotConfig.ready] 正在初始化 LangChain Agent ---")
        
        from langchain_community.utilities import SQLDatabase
        from langchain.agents import create_sql_agent
        from langchain.agents.agent_toolkits import SQLDatabaseToolkit
        
        # 引用專案中的其他模組
        from .custom_llm_adapter import CustomMicronChat
        from .db_helper import SQLHelper

        # 1. 初始化資料庫
        sql_helper = SQLHelper(database_alias='MTBOI45')
        engine = sql_helper.get_sqlalchemy_engine()
        db = SQLDatabase(engine=engine)
        
        # 2. 初始化 LLM
        llm = CustomMicronChat(model_name="gpt-4.1", temperature=0)
        
        # 3. 建立 Agent 並將其存儲在 AppConfig 類別屬性中
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        ChatbotConfig.agent_executor = create_sql_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=True,
            agent_type="openai-tools",
        )
        print("--- Agent 初始化完成，並已存儲在 AppConfig 中 ---")


# chatbot/__init__.py
# --------------------
# 告訴 Django 使用我們自訂的 AppConfig

default_app_config = 'chatbot.apps.ChatbotConfig'


# chatbot/services.py
# --------------------
# 核心服務現在從 AppConfig 獲取 Agent，而不是使用全域變數。

from django.apps import apps

def ask_question(question: str) -> str:
    """
    接收一個問題，使用 Agent 執行並返回答案。
    """
    if not question:
        return "請輸入您的問題。"
        
    try:
        # 從準備好的 AppConfig 中獲取 Agent 單例
        agent_config = apps.get_app_config('chatbot')
        agent = agent_config.agent_executor

        if agent is None:
             raise RuntimeError("Chatbot Agent 尚未被初始化。")

        result = agent.invoke({"input": question})
        answer = result.get("output", "抱歉，我無法處理您的請求。")
        return answer
    except Exception as e:
        print(f"執行 Agent 時發生錯誤: {e}")
        return "抱歉，系統在處理您的請求時發生了預期外的錯誤。"


# chatbot/views.py
# -----------------
# View 的部分不需要任何改變，因為它只跟 service 互動。

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .services import ask_question

@csrf_exempt
@require_http_methods(["POST"])
def ask_chatbot_api(request):
    """
    一個 API View，接收前端傳來的問題並回傳 AI 的答案。
    """
    try:
        data = json.loads(request.body)
        question = data.get('question', '')

        if not question:
            return JsonResponse({'error': '問題不能為空。'}, status=400)

        answer = ask_question(question)
        
        return JsonResponse({'answer': answer})

    except json.JSONDecodeError:
        return JsonResponse({'error': '無效的 JSON 格式。'}, status=400)
    except Exception as e:
        print(f"API View 發生錯誤: {e}")
        return JsonResponse({'error': '伺服器內部錯誤。'}, status=500)


# chatbot/urls.py
# ----------------
# URL 的部分也不需要改變。

from django.urls import path
from .views import ask_chatbot_api

urlpatterns = [
    path('ask/', ask_chatbot_api, name='ask_chatbot_api'),
]

# 在您的專案主 urls.py 中，加入以下路由：
# from django.urls import path, include
#
# urlpatterns = [
#     ...
#     path('api/chatbot/', include('chatbot.urls')),
#     ...
# ]
