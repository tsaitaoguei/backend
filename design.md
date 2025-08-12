
# 需求分析
## 核心功能
- **AI 聊天框**：僅與 AI 對話，不需要多人聊天  
- **浮動設計**：右下角浮動窗口  
- **串流回應**：逐字顯示 AI 回答  
- **LangChain 整合**：與你的 MicronLLMService 結合  
- **數據庫整合**：LangChain 可以查詢 MSSQL 數據  
---
## 前端需求規劃
### Angular 組件架構
```
ChatWidget (浮動聊天框)
├── ChatToggle (開關按鈕)
├── ChatWindow (聊天窗口)
│   ├── MessageList (消息列表)
│   ├── TypingIndicator (打字效果)
│   └── MessageInput (輸入框)
└── ChatService (WebSocket 服務)
```
---
## 後端需求規劃
### Django 架構
```
Backend Architecture
├── WebSocket Consumer (處理即時通信)
├── LangChain Service (AI 對話管理)
│   ├── Custom LLM (包裝 MicronLLMService)
│   ├── Memory Management (對話記憶)
│   ├── SQL Agent (數據庫查詢能力)
│   └── Prompt Templates (提示詞模板)
├── Streaming Service (串流回應處理)
└── Database Integration (MSSQL 查詢)
```
---
## 後端技術需求
- **Django Channels**：WebSocket 支持  
- **LangChain 自定義 LLM**：包裝你的 MicronLLMService  
- **LangChain SQL Agent**：讓 AI 能查詢數據庫  
- **串流處理**：模擬逐字回應  
- **會話管理**：保存對話歷史  
---
## 數據流程設計
### 用戶發送消息流程
```
用戶輸入 → WebSocket → Django Consumer → LangChain Service
```
### AI 處理流程
```
LangChain Service → 判斷是否需要查詢數據庫
├── 需要查詢 → SQL Agent → SQLHelper → 返回數據 → 生成回答
└── 不需要查詢 → 直接調用 MicronLLMService → 生成回答
```
### 串流回應
```
AI 回答 → 分塊處理 → WebSocket 逐步發送 → 前端逐字顯示
```
---

## 技術整合點
### LangChain + MicronLLMService
- 創建自定義 LLM 類繼承 `langchain.llms.base.LLM`  
- 在 `_call` 方法中調用你的 MicronLLMService  
- 使用 LangChain 的 Memory 管理對話歷史  
### LangChain + SQLHelper
- 使用 `langchain.agents.create_sql_agent`  
- 配置 SQLAlchemy 引擎連接 MSSQL  
- 讓 AI 能夠理解數據庫結構並生成 SQL 查詢  
---
## 串流實現策略
- **後端**：將完整回應分割成小塊，通過 WebSocket 逐步發送  
- **前端**：接收後逐字顯示  
---
## UI/UX 設計要點
### 浮動聊天框特性
- **位置**：右下角固定  
- **狀態**：最小化 / 展開  
- **尺寸**：適中，不遮擋主要內容  
- **動畫**：平滑的展開 / 收起效果  
- **響應式**：手機端適配  
### 聊天體驗
- **打字效果**：模擬真人打字速度  
- **狀態指示**：顯示 AI 正在思考  
- **錯誤處理**：網絡斷線、API 錯誤提示  
- **歷史記錄**：保存最近的對話  
