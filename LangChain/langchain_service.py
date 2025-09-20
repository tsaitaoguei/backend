from langchain.llms.base import LLM
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from typing import Optional, List, Any, AsyncIterator
import asyncio
import json
import re
from .models import ChatSession, ChatMessage
from services.llm_service import MicronLLMService
from channels.db import database_sync_to_async

class MicronCustomLLM(LLM):
    """Custom LLM wrapper for MicronLLMService"""
    
    # 正確定義字段
    system_prompt: str = "You are a professional AI assistant. Please provide accurate and helpful responses."
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 在初始化後設置服務，而不是作為字段
        self._micron_service = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Micron service"""
        try:
            self._micron_service = MicronLLMService()
            print("MicronLLMService initialized successfully")
        except Exception as e:
            print(f"Failed to initialize MicronLLMService: {str(e)}")
            self._micron_service = None
    
    @property
    def _llm_type(self) -> str:
        return "micron_custom"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None, is_stream:bool = False):
        """Synchronous call to real API with optional streaming"""
        try:
            if not self._micron_service:
                return "Sorry, the AI service is not available."
                
            try:
                # 先嘗試帶 is_stream 參數的調用
                response = self._micron_service.generate_ai_response(
                    sys_prompt=self.system_prompt,
                    user_prompt=prompt,
                    model="gpt-4.1",
                    temperature=0.7,
                    top_p=0.8,
                    max_tokens=2000,
                    stop_words=stop or ["User:", "AI:"],
                    is_stream="True" if is_stream else "False"
                )
            except TypeError as e:
                # 如果 is_stream 參數不被支持，退回到不帶參數的調用
                if "is_stream" in str(e):
                    print("Warning: is_stream parameter not supported, falling back to standard call")
                    response = self._micron_service.generate_ai_response(
                        sys_prompt=self.system_prompt,
                        user_prompt=prompt,
                        model="gpt-4.1",
                        temperature=0.7,
                        top_p=0.8,
                        max_tokens=2000,
                        stop_words=stop or ["User:", "AI:"]
                    )
                else:
                    raise e
            
            # 處理不同的響應格式
            if response:
                if isinstance(response, dict):
                    if 'choices' in response:
                        return response
                elif isinstance(response, str):
                    return response
            
            return "Sorry, the AI service returned an unexpected response format."
                
        except Exception as e:
            print(f"LLM API call error: {str(e)}")
            return f"An error occurred while processing your request: {str(e)}"
    
    async def _acall(self, prompt: str, stop: Optional[List[str]] = None, is_stream: bool = False) -> str:
        """Asynchronous call - execute sync call in thread pool"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._call, prompt, stop, is_stream
        )
    
    async def astream_response(self, prompt: str) -> AsyncIterator[str]:
        """Real streaming response with word-by-word display"""
        try:
            if not self._micron_service:
                yield "Sorry, the AI service is not available."
                return
            
            # 使用真正的流式 API
            try:
                response = await self._acall(prompt, is_stream=True)
                
                if response and isinstance(response, dict) and 'choices' in response:
                    content = response['choices'][0]['message']['content']
                    
                    # 逐字符增量顯示
                    for i, char in enumerate(content):
                        yield char  # 只返回當前字符，不是累積文本
                        
                        # 控制顯示速度
                        if char in [' ', '\n', '。', '！', '？', '.', '!', '?']:
                            await asyncio.sleep(0.05)
                        else:
                            await asyncio.sleep(0.02)
                    return 
            except TypeError as e:
                response = await self._acall(prompt, is_stream=False)
                if isinstance(response, str):
                    chunks = self._smart_chunk_response(response)
                    for chunk in chunks:
                        yield chunk
                        await asyncio.sleep(0.1)
                else:
                    yield "Sorry, received an unexpected response format."
                    
        except Exception as e:
            print(f"Stream API call error: {str(e)}")
            yield f"Error: {str(e)}"
    
    def _smart_chunk_response(self, response: str) -> List[str]:
        """Smart chunking - split by sentences and punctuation"""
        # Split by sentences (English and Chinese punctuation)
        sentences = re.split(r'([。！？\.!?])', response)
        chunks = []
        current_chunk = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i] if i < len(sentences) else ""
            punctuation = sentences[i+1] if i+1 < len(sentences) else ""
            
            full_sentence = sentence + punctuation
            
            if len(current_chunk + full_sentence) > 50:  # Control chunk size
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = full_sentence
            else:
                current_chunk += full_sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

class LangChainChatService:
    """Main chat service class"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.llm = MicronCustomLLM()
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
    
    @database_sync_to_async
    def _load_session_history_sync(self):
        """Load session history from database - sync version"""
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
    
    async def _load_session_history(self):
        """Load session history from database - async wrapper"""
        history_data = await self._load_session_history_sync()
        
        for msg_data in history_data:
            if msg_data['type'] == 'user':
                self.memory.chat_memory.add_user_message(msg_data['content'])
            elif msg_data['type'] == 'ai':
                self.memory.chat_memory.add_ai_message(msg_data['content'])
    
    @database_sync_to_async
    def _get_or_create_session_sync(self):
        """Get or create session - sync version"""
        session, created = ChatSession.objects.using('MTBOI45').get_or_create(
            session_id=self.session_id,
            defaults={}
        )
        return session
    
    @database_sync_to_async
    def _save_user_message_sync(self, session, message):
        """Save user message - sync version"""
        user_message = ChatMessage.objects.using('MTBOI45').create(
            session=session,
            message_type='user',
            content=message
        )
        return user_message
    
    @database_sync_to_async
    def _save_ai_message_sync(self, session, content, metadata):
        """Save AI message - sync version"""
        ai_message = ChatMessage.objects.using('MTBOI45').create(
            session=session,
            message_type='ai',
            content=content,
            metadata=metadata
        )
        return ai_message
    
    async def process_user_message(self, message: str, user=None) -> AsyncIterator[dict]:
        """Process user message and return streaming response"""
        try:
            # Load session history first
            await self._load_session_history()
            
            # Get or create session
            session = await self._get_or_create_session_sync()
            
            # Save user message
            user_message = await self._save_user_message_sync(session, message)
            
            # Add to memory
            self.memory.chat_memory.add_user_message(message)
            
            # Prepare prompt
            prompt = self._build_prompt(message)
            
            # Stream generate AI response
            full_response = ""
            chunk_index = 0
            
            async for chunk in self.llm.astream_response(prompt):
                full_response += chunk
                chunk_index += 1
                
                yield {
                    "type": "ai_chunk",
                    "session_id": str(self.session_id),
                    "content": chunk,
                    "chunk_index": chunk_index,
                    "is_complete": False
                }
            
            # Save complete AI response
            ai_message = await self._save_ai_message_sync(
                session, 
                full_response,
                {
                    "token_count": len(full_response.split()),
                    "processing_time": "simulated_time"
                }
            )
            
            # Add to memory
            self.memory.chat_memory.add_ai_message(full_response)
            
            # Send completion signal
            yield {
                "type": "ai_complete",
                "session_id": str(self.session_id),
                "message_id": str(ai_message.message_id),
                "full_response": full_response,
                "token_count": len(full_response.split())
            }
            
        except Exception as e:
            print(f"Error in process_user_message: {str(e)}")
            yield {
                "type": "error",
                "error_code": "PROCESSING_ERROR",
                "message": "An error occurred while processing the message",
                "details": str(e)
            }
    
    def _build_prompt(self, message: str) -> str:
        """Build prompt with conversation context"""
        history = self.memory.chat_memory.messages
        
        # Build conversation history
        conversation_history = []
        for msg in history[-6:]:  # Only take the last 6 messages
            if isinstance(msg, HumanMessage):
                conversation_history.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conversation_history.append(f"Assistant: {msg.content}")
        
        # If there's history, include it in the prompt
        if conversation_history:
            context = "\n".join(conversation_history)
            return f"Based on the following conversation history, answer the user's new question:\n\n{context}\n\nUser: {message}"
        else:
            return message