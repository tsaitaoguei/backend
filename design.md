
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

---

## 前端架構設計 (Angular)
### Angular 組件架構
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
```
typescript
// ChatService - WebSocket 通信
// SessionService - 會話管理  
// MessageService - 消息處理
// StorageService - 本地存儲
```
---
## 後端需求規劃
### Django 架構
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