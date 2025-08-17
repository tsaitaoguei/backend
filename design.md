# File: c:\MTB\gitgub\backend\design.md
# MTB OPS AI 聊天系統設計文檔

## 需求分析
### 核心功能
- **AI 聊天框**：僅與 AI 對話，不需要多人聊天  
- **浮動設計**：右下角浮動窗口，不干擾主要工作流程  
- **串流回應**：逐字顯示 AI 回答，提供類似 ChatGPT/Copilot 的體驗  
- **LangChain 整合**：與現有 MicronLLMService 深度整合  
- **會話管理**：支持多個獨立對話會話  
- **數據持久化**：會話和消息存儲到 MSSQL 數據庫
- **未來擴展**：預留數據庫查詢和多模態功能接口 

### 技術棧
- **前端**：Angular + TypeScript + WebSocket Client
- **後端**：Django + Django Channels + LangChain
- **數據庫**：MSSQL Server
- **通信協議**：WebSocket (即時串流)
- **AI 服務**：MicronLLMService (現有)
- **消息隊列**：Redis (遠程部署)

---

## Redis 架構設計與配置

### 🏗️ 架構設計
```
Web Server (Windows)              Docker Server (RHEL)
┌─────────────────────┐       ┌──────────────────────────┐
│  MTB OPS Django     │       │  Redis Container         │
│  - Django Channels  │       │  - Host: 10.20.176.207   │
│  - WebSocket        │<─────>│  - Port: 6379            │
│  - IP: 10.34.172.229│       │  - Password required     │
└─────────────────────┘       └──────────────────────────┘
```

### 🐳 RHEL Docker 服務器 Redis 部署

#### 1. Redis 配置文件
```conf
# File: /opt/redis/config/redis.conf

# 網絡配置 - 允許遠程連接
bind 0.0.0.0                   # 監聽所有網絡接口
port 6379                      # Redis 服務端口
timeout 300                    # 客戶端閒置5分鐘後斷開

# 安全配置 - 必須設置密碼
protected-mode yes             # 啟用保護模式
requirepass XXX                # 設置強密碼

# 持久化配置 - 適合聊天應用
save 900 1                     # 15分鐘內1個key變化就保存
save 300 10                    # 5分鐘內10個key變化就保存
save 60 10000                  # 1分鐘內10000個key變化就保存
dbfilename mtbops-dump.rdb     # 數據庫備份文件名
dir /data                      # 數據文件存放目錄

# 日誌配置
loglevel notice                # 日誌級別：一般信息
logfile /var/log/redis/redis.log # 日誌文件路徑

# 內存配置 - 根據服務器配置調整
maxmemory 2gb                  # 最大使用2GB內存
maxmemory-policy allkeys-lru   # 內存滿時使用LRU淘汰策略

# 網絡優化
tcp-keepalive 300              # TCP保活時間300秒
tcp-backlog 511                # TCP監聽隊列大小

# 性能優化
databases 16                   # 默認數據庫數量
```
#### 2. Docker 容器部署
```
# 創建目錄結構
sudo mkdir -p /opt/redis/{config,data,logs}

# 設置權限
sudo chown -R 999:999 /opt/redis/data
sudo chown -R 999:999 /opt/redis/logs

# 啟動 Redis 容器
docker run -d \
  --name mtbops-redis \
  -p 6379:6379 \
  --restart unless-stopped \
  -v /opt/redis/config/redis.conf:/usr/local/etc/redis/redis.conf \
  -v /opt/redis/data:/data \
  -v /opt/redis/logs:/var/log/redis \
  redis:latest \
  redis-server /usr/local/etc/redis/redis.conf

# 檢查容器狀態
docker ps | grep mtbops-redis
docker logs mtbops-redis
```

#### 3. 防火牆配置
```
# 開放 Redis 端口
sudo firewall-cmd --permanent --add-port=6379/tcp
sudo firewall-cmd --reload

# 檢查端口狀態
sudo firewall-cmd --list-ports
sudo netstat -tlnp | grep 6379
```
### 📊 監控和維護
#### 1. 性能監控
```
# 監控 Redis 性能
docker exec mtbops-redis redis-cli INFO stats
docker exec mtbops-redis redis-cli INFO memory
docker exec mtbops-redis redis-cli INFO clients

# 監控慢查詢
docker exec mtbops-redis redis-cli SLOWLOG GET 10
```

#### 2. 備份策略
```
# 手動備份
docker exec mtbops-redis redis-cli BGSAVE

# 定時備份腳本
#!/bin/bash
# File: /opt/redis/backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
docker exec mtbops-redis redis-cli BGSAVE
cp /opt/redis/data/mtbops-dump.rdb /opt/redis/backup/mtbops-dump_$DATE.rdb

# 設置 crontab
# 0 2 * * * /opt/redis/backup.sh
```

---

## 前端架構設計 (Angular)
### 組件架構
```
ChatWidget (浮動聊天框根組件)
├── ChatToggle (開關按鈕)
│   ├── 最小化狀態顯示
│   └── 未讀消息提示
├── ChatWindow (聊天窗口主體)
│   ├── ChatHeader (標題欄)
│   │   ├── 會話標題
│   │   ├── 最小化按鈕
│   │   └── 關閉按鈕
│   ├── MessageList (消息列表)
│   │   ├── UserMessage (用戶消息組件)
│   │   ├── AiMessage (AI消息組件)
│   │   └── TypingIndicator (打字效果)
│   └── MessageInput (輸入框)
│       ├── 文本輸入區
│       ├── 發送按鈕
│       └── 字數統計
└── ChatService (WebSocket 通信服務)
    ├── 連接管理
    ├── 消息發送/接收
    ├── 斷線重連
    └── 錯誤處理
```

### 核心服務
```typescript
// ChatService - WebSocket 通信
// SessionService - 會話管理  
// MessageService - 消息處理
// StorageService - 本地存儲
```

---

## 後端架構設計 (Django)
### 整體架構
```
Backend Architecture
├── Django Channels (WebSocket 支持)
│   ├── ChatConsumer (WebSocket 消費者)
│   ├── Routing (WebSocket 路由)
│   └── Middleware (認證、CORS)
├── REST API Views (HTTP 端點)
│   ├── Session Management (會話管理)
│   ├── History Retrieval (歷史記錄)
│   └── User Management (用戶管理)
├── LangChain Service (AI 對話管理)
│   ├── MicronCustomLLM (包裝 MicronLLMService)
│   ├── ConversationMemory (對話記憶)
│   ├── Prompt Templates (提示詞模板)
│   └── Stream Handler (串流處理)
├── Database Models (MSSQL)
│   ├── ChatSession (會話模型)
│   ├── ChatMessage (消息模型)
│   └── User (用戶模型)
└── Background Tasks (異步任務)
    ├── Message Processing (消息處理)
    └── Session Cleanup (會話清理)
```

### 核心組件
```python
# WebSocket Consumer
class ChatConsumer(AsyncWebsocketConsumer)

# LangChain 整合
class MicronCustomLLM(LLM)
class LangChainChatService

# 數據模型
class ChatSession(models.Model)
class ChatMessage(models.Model)
```

---

## 🔧 技術難點與解決方案

### 問題1: LangChain LLM 字段驗證錯誤
#### 問題描述
```
Error: "MicronCustomLLM" object has no field "micron_service"
```

#### 根本原因
LangChain 的 `LLM` 基類繼承自 Pydantic 的 `BaseModel`，具有嚴格的字段驗證機制：
- **字段必須預先定義**：不能動態添加實例屬性
- **類型註解必須明確**：所有字段需要正確的類型聲明
- **初始化順序嚴格**：必須遵循 Pydantic 的初始化流程

#### 錯誤示例
```python
# ❌ 這樣會報錯
class MicronCustomLLM(LLM):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.micron_service = MicronLLMService()  # Pydantic 拒絕未定義字段
```

#### 解決方案對比

##### 方案1: 私有屬性 (推薦)
```python
# ✅ 推薦方案：使用私有屬性
class MicronCustomLLM(LLM):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 私有屬性不受 Pydantic 驗證限制
        self._micron_service = None
        self._system_prompt = "You are a helpful assistant."
        self._initialize_service()
    
    def _initialize_service(self):
        """延遲初始化，避免構造函數錯誤"""
        try:
            self._micron_service = MicronLLMService()
        except Exception as e:
            print(f"Service init failed: {e}")
```

##### 方案2: __dict__ 繞過 (不推薦)
```python
# ⚠️ 可行但不推薦：直接操作 __dict__
class MicronCustomLLM(LLM):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 繞過 Pydantic 驗證，但破壞封裝性
        self.__dict__['_micron_service'] = MicronLLMService()
```

##### 方案3: 正式字段定義 (複雜)
```python
# ✅ 可行但複雜：預先定義所有字段
class MicronCustomLLM(LLM):
    micron_service: Any = None  # 需要導入 typing.Any
    system_prompt: str = "default"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.micron_service = MicronLLMService()
```

#### 為什麼推薦私有屬性方案？
1. **符合 Python 慣例** - 私有屬性是標準做法
2. **不破壞封裝性** - 保持代碼清晰可維護
3. **避免 Pydantic 衝突** - 私有屬性不受驗證限制
4. **未來兼容性好** - LangChain 更新不太可能影響私有屬性

#### 完整實現示例
```python
class MicronCustomLLM(LLM):
    """Custom LLM wrapper for MicronLLMService"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._micron_service = None
        self._system_prompt = "You are a professional AI assistant."
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Micron service with error handling"""
        try:
            from services.llm_service import MicronLLMService
            self._micron_service = MicronLLMService()
            print("MicronLLMService initialized successfully")
        except Exception as e:
            print(f"Failed to initialize MicronLLMService: {str(e)}")
            self._micron_service = None
    
    @property
    def _llm_type(self) -> str:
        return "micron_custom"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Call real Micron API"""
        try:
            if not self._micron_service:
                return "Sorry, the AI service is not available."
                
            response = self._micron_service.generate_ai_response(
                sys_prompt=self._system_prompt,
                user_prompt=prompt,
                model="gpt-4.1",
                temperature=0.7,
                max_tokens=2000,
                stop_words=stop or ["User:", "AI:"]
            )
            
            # Handle different response formats
            if response:
                if isinstance(response, dict):
                    if 'choices' in response:
                        return response['choices'][0]['message']['content']
                    elif 'content' in response:
                        return response['content']
                elif isinstance(response, str):
                    return response
            
            return "Sorry, the AI service returned an unexpected response."
            
        except Exception as e:
            print(f"LLM API call error: {str(e)}")
            return f"An error occurred: {str(e)}"
```

#### 關鍵學習點
- **理解框架限制**：不同框架有不同的字段管理機制
- **選擇合適方案**：在可行性、可維護性、標準性之間平衡
- **錯誤處理重要**：服務初始化可能失敗，需要優雅降級
- **調試信息有用**：添加日誌幫助排查問題

### 問題2: Django Channels 異步上下文錯誤
#### 問題描述
```
Error: You cannot call this from an async context - use a thread or sync_to_async.
```

#### 根本原因
Django Channels 的 WebSocket Consumer 運行在**異步上下文**中，但 Django ORM 是**同步設計**的：
- **異步環境限制**：WebSocket Consumer 繼承自 `AsyncWebsocketConsumer`
- **ORM 同步特性**：`Model.objects.create()`, `Model.objects.get()` 等都是同步操作
- **上下文衝突**：在異步函數中直接調用同步 ORM 會被 Django 阻止

#### 錯誤示例
```python
# ❌ 這樣會報錯
class ChatConsumer(AsyncWebsocketConsumer):
    async def receive(self, text_data):
        # 在異步上下文中直接調用同步 ORM
        session = ChatSession.objects.get(session_id=self.session_id)  # 錯誤！
        message = ChatMessage.objects.create(...)  # 錯誤！
```

#### 解決方案：使用 database_sync_to_async

##### 核心概念
`database_sync_to_async` 是 Django Channels 提供的裝飾器，用於：
- **包裝同步函數**：將同步的數據庫操作包裝成異步函數
- **線程池執行**：在後台線程池中執行同步操作
- **保持事務安全**：確保數據庫事務的正確性

##### 正確實現方式
```python
# ✅ 正確方案：分離同步和異步操作
from channels.db import database_sync_to_async

class LangChainChatService:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.llm = MicronCustomLLM()
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
    
    # 步驟1：創建同步版本的數據庫操作
    @database_sync_to_async
    def _load_session_history_sync(self):
        """Load session history - 同步版本"""
        try:
            session = ChatSession.objects.using('MTBOI45').get(session_id=self.session_id)
            messages = session.messages.order_by('created_at')
            
            history_data = []
            for message in messages:
                history_data.append({
                    'type': message.message_type,
                    'content': message.content
                })
            return history_data
        except ChatSession.DoesNotExist:
            return []
    
    @database_sync_to_async
    def _get_or_create_session_sync(self):
        """Get or create session - 同步版本"""
        session, created = ChatSession.objects.using('MTBOI45').get_or_create(
            session_id=self.session_id,
            defaults={}
        )
        return session
    
    @database_sync_to_async
    def _save_user_message_sync(self, session, message):
        """Save user message - 同步版本"""
        user_message = ChatMessage.objects.using('MTBOI45').create(
            session=session,
            message_type='user',
            content=message
        )
        return user_message
    
    @database_sync_to_async
    def _save_ai_message_sync(self, session, content, metadata):
        """Save AI message - 同步版本"""
        ai_message = ChatMessage.objects.using('MTBOI45').create(
            session=session,
            message_type='ai',
            content=content,
            metadata=metadata
        )
        return ai_message
    
    # 步驟2：在異步函數中調用包裝後的同步操作
    async def _load_session_history(self):
        """Load session history - 異步包裝器"""
        history_data = await self._load_session_history_sync()
        
        for msg_data in history_data:
            if msg_data['type'] == 'user':
                self.memory.chat_memory.add_user_message(msg_data['content'])
            elif msg_data['type'] == 'ai':
                self.memory.chat_memory.add_ai_message(msg_data['content'])
    
    async def process_user_message(self, message: str, user=None) -> AsyncIterator[dict]:
        """Process user message - 主要異步函數"""
        try:
            # 所有數據庫操作都使用 await 調用異步版本
            await self._load_session_history()
            session = await self._get_or_create_session_sync()
            user_message = await self._save_user_message_sync(session, message)
            
            # 其他業務邏輯...
            
            ai_message = await self._save_ai_message_sync(session, full_response, metadata)
            
        except Exception as e:
            print(f"Error in process_user_message: {str(e)}")
```

#### 設計模式總結

##### 1. 分離原則
```python
# 同步函數：純數據庫操作，使用 @database_sync_to_async 裝飾
@database_sync_to_async
def _database_operation_sync(self, params):
    return Model.objects.create(...)

# 異步函數：業務邏輯，調用包裝後的同步函數
async def business_logic_async(self):
    result = await self._database_operation_sync(params)
    return result
```

##### 2. 命名約定
- **同步函數**：`_operation_name_sync()`
- **異步包裝器**：`_operation_name()` 或 `operation_name_async()`
- **主要業務函數**：`process_something()`, `handle_something()`

##### 3. 錯誤處理
```python
async def safe_database_operation(self):
    try:
        result = await self._database_operation_sync()
        return result
    except Exception as e:
        print(f"Database error: {str(e)}")
        # 提供降級方案或重新拋出異常
        raise
```

#### 為什麼這樣設計？
1. **性能考慮** - 避免阻塞異步事件循環
2. **安全考慮** - 保持數據庫事務的完整性
3. **架構清晰** - 明確分離同步和異步操作
4. **可維護性** - 每個函數職責單一，易於測試和調試

#### 常見陷阱和注意事項
```python
# ❌ 錯誤：忘記使用 await
async def wrong_way(self):
    result = self._database_operation_sync()  # 返回 coroutine 對象，不是實際結果

# ✅ 正確：使用 await
async def correct_way(self):
    result = await self._database_operation_sync()  # 獲得實際結果

# ❌ 錯誤：在同步函數中混合異步操作
@database_sync_to_async
def mixed_operations_wrong(self):
    # 不要在同步函數中調用異步操作
    await some_async_function()  # 這會報錯

# ✅ 正確：保持同步函數純粹
@database_sync_to_async
def pure_sync_operation(self):
    # 只做同步的數據庫操作
    return Model.objects.create(...)
```

#### 關鍵學習點
- **理解異步上下文**：WebSocket Consumer 是異步環境，需要特殊處理同步操作
- **正確使用裝飾器**：`@database_sync_to_async` 是解決方案的核心
- **分離關注點**：數據庫操作和業務邏輯分開處理
- **命名規範**：清晰的命名幫助區分同步和異步函數
- **錯誤處理**：每個異步操作都需要適當的異常處理

---

## 數據庫設計 (MSSQL)
### 表結構
```sql
-- 聊天會話表
CREATE TABLE chat_sessions (
    session_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    user_id INT NULL,
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE(),
    is_active BIT DEFAULT 1,
    session_title NVARCHAR(255) NULL,
    FOREIGN KEY (user_id) REFERENCES auth_user(id)
);

-- 聊天消息表  
CREATE TABLE chat_messages (
    message_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    session_id UNIQUEIDENTIFIER NOT NULL,
    message_type NVARCHAR(10) NOT NULL, -- 'user', 'ai', 'system'
    content NTEXT NOT NULL,
    metadata NVARCHAR(MAX) NULL, -- JSON 格式
    created_at DATETIME2 DEFAULT GETDATE(),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);

-- 索引優化
CREATE INDEX IX_chat_messages_session_created ON chat_messages(session_id, created_at);
CREATE INDEX IX_chat_sessions_user_active ON chat_sessions(user_id, is_active);
```

---

## WebSocket API 設計
### 連接端點
```
ws://localhost:8000/ws/chat/{session_id}/
```

### 消息格式規範
```json
// 客戶端 → 服務器 (用戶消息)
{
  "type": "user_message",
  "session_id": "uuid-string",
  "message": "用戶輸入的內容",
  "timestamp": "2024-01-01T12:00:00Z"
}

// 服務器 → 客戶端 (AI 串流回應)
{
  "type": "ai_chunk",
  "session_id": "uuid-string",
  "content": "AI回應的片段",
  "chunk_index": 1,
  "is_complete": false
}

// 服務器 → 客戶端 (回應完成)
{
  "type": "ai_complete",
  "session_id": "uuid-string",
  "message_id": "uuid-string",
  "full_response": "完整的AI回應",
  "token_count": 150
}

// 錯誤處理
{
  "type": "error",
  "error_code": "PROCESSING_ERROR",
  "message": "處理消息時發生錯誤",
  "details": "具體錯誤信息"
}

// 系統消息
{
  "type": "system",
  "message": "連接已建立",
  "session_info": {
    "session_id": "uuid-string",
    "created_at": "2024-01-01T12:00:00Z"
  }
}
```

---

## REST API 設計 (輔助功能)
### 核心端點
```
POST /api/chat/session/create/     # 創建新會話
GET  /api/chat/session/{id}/       # 獲取會話信息
GET  /api/chat/session/{id}/history/ # 獲取對話歷史
PUT  /api/chat/session/{id}/       # 更新會話 (如標題)
DELETE /api/chat/session/{id}/     # 刪除會話
GET  /api/chat/sessions/           # 獲取用戶所有會話
```

### 響應格式
```json
// 創建會話響應
{
  "session_id": "uuid-string",
  "created_at": "2024-01-01T12:00:00Z",
  "websocket_url": "ws://localhost:8000/ws/chat/{session_id}/"
}

// 歷史記錄響應
{
  "session_id": "uuid-string",
  "messages": [
    {
      "message_id": "uuid-string",
      "type": "user",
      "content": "用戶消息",
      "created_at": "2024-01-01T12:00:00Z"
    },
    {
      "message_id": "uuid-string", 
      "type": "ai",
      "content": "AI回應",
      "created_at": "2024-01-01T12:00:01Z"
    }
  ],
  "total_count": 2
}
```

---

## 數據流程設計
### 完整對話流程
```
1. 用戶打開聊天框
   ↓
2. 前端調用 POST /api/chat/session/create/ 創建會話
   ↓
3. 前端建立 WebSocket 連接 ws://localhost:8000/ws/chat/{session_id}/
   ↓
4. 用戶輸入消息 → 通過 WebSocket 發送
   ↓
5. Django Consumer 接收消息 → 調用 LangChainChatService
   ↓
6. LangChain 處理 → 調用 MicronLLMService → 生成回應
   ↓
7. AI 回應分塊 → 通過 WebSocket 串流發送
   ↓
8. 前端接收串流 → 逐字顯示 → 保存到本地
   ↓
9. 對話完成 → 消息保存到 MSSQL 數據庫
```

### 錯誤處理流程
```
WebSocket 斷線 → 自動重連 (最多3次)
API 調用失敗 → 顯示錯誤提示 + 重試按鈕
AI 處理超時 → 超時提示 + 取消按鈕
數據庫錯誤 → 降級到內存存儲 + 警告提示
```

---

## 技術整合點
### LangChain + MicronLLMService
```python
class MicronCustomLLM(LLM):
    """自定義 LLM 包裝 MicronLLMService"""
    
    def _call(self, prompt: str, **kwargs) -> str:
        # 調用現有的 MicronLLMService
        return self.micron_service.generate_ai_response(...)
    
    async def _acall(self, prompt: str, **kwargs) -> str:
        # 異步版本，支持串流
        pass

class LangChainChatService:
    """聊天服務主類"""
    
    def __init__(self, session_id: str):
        self.llm = MicronCustomLLM()
        self.memory = ConversationBufferWindowMemory(k=10)
    
    async def stream_response(self, message: str):
        """串流處理用戶消息"""
        # 實現串流邏輯
        pass
```

### Django Channels 整合
```python
# settings.py
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}

# routing.py
websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<session_id>[^/]+)/$', ChatConsumer.as_asgi()),
]
```

---

## 實現階段規劃
### Phase 1: 核心功能 (2-3 週)
- ✅ Django Channels 環境設置
- ✅ MSSQL 數據庫模型設計
- ✅ WebSocket Consumer 基礎實現
- ✅ LangChain + MicronLLMService 整合
- ⏳ Angular 聊天組件開發
- ⏳ WebSocket 前後端聯調
- ⏳ 基礎串流回應實現

### Phase 2: 用戶體驗優化 (1-2 週)
- 🔄 打字效果和動畫優化
- 🔄 斷線重連機制
- 🔄 錯誤處理和用戶提示
- 🔄 會話管理界面
- 🔄 響應式設計適配

### Phase 3: 高級功能 (2-3 週)
- 🔄 數據庫查詢能力 (SQL Agent)
- 🔄 多會話管理
- 🔄 消息搜索功能
- 🔄 用戶偏好設置
- 🔄 性能優化和監控

### Phase 4: 擴展功能 (未來)
- 🔄 多模態支持 (圖片、文件)
- 🔄 語音輸入/輸出
- 🔄 聊天記錄導出
- 🔄 AI 助手個性化

---

## UI/UX 設計要點
### 浮動聊天框特性
- **位置**：右下角固定，距離邊緣 20px
- **尺寸**：最小化時 60x60px，展開時 400x600px
- **狀態**：最小化 / 展開 / 隱藏
- **動畫**：300ms 平滑過渡效果
- **層級**：z-index 9999，始終在最上層
- **響應式**：手機端全屏顯示

### 聊天體驗設計
- **打字效果**：每個字符間隔 30-50ms
- **狀態指示**：
  - 連接中：脈衝動畫
  - AI 思考中：三點跳動動畫
  - 錯誤狀態：紅色邊框提示
- **消息氣泡**：
  - 用戶消息：右對齊，藍色背景
  - AI 消息：左對齊，灰色背景
  - 系統消息：居中，淺色背景
- **交互反饋**：
  - 發送按鈕：發送中禁用
  - 輸入框：字數統計和限制
  - 滾動：自動滾動到最新消息

### 錯誤處理設計
- **網絡錯誤**：顯示重連按鈕
- **API 錯誤**：顯示具體錯誤信息
- **超時錯誤**：顯示取消和重試選項
- **降級體驗**：離線模式提示

---

## 性能和安全考慮
### 性能優化
- **前端**：虛擬滾動、消息分頁加載
- **後端**：連接池、消息隊列、緩存策略
- **數據庫**：索引優化、分區表設計
- **網絡**：消息壓縮、斷線重連優化

### 安全措施
- **認證**：JWT Token 驗證
- **授權**：會話所有權驗證
- **輸入驗證**：消息長度和內容過濾
- **速率限制**：防止消息轟炸
- **數據加密**：敏感信息加密存儲

---

## 監控和維護
### 關鍵指標
- WebSocket 連接數和穩定性
- 消息處理延遲和成功率
- AI 服務調用次數和響應時間
- 數據庫查詢性能
- 用戶活躍度和滿意度

### 日誌記錄
- 用戶操作日誌
- 系統錯誤日誌
- 性能監控日誌
- AI 服務調用日誌

---

## 部署架構
### 開發環境
- Django Development Server + Channels
- Angular Development Server
- Local MSSQL Server

### 生產環境
- Django + Gunicorn + Daphne
- Nginx (反向代理 + 靜態文件)
- MSSQL Server (高可用配置)
- Redis (Channel Layer)
- Docker 容器化部署
