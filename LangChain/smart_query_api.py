from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import json
import asyncio
import logging
from typing import Dict, Any

from .database_aware_service import DatabaseAwareChatService
from .models import ChatSession, ChatMessage, QueryHistory
from .db_schema_helper import DjangoSchemaHelper
from .query_history_api import log_query_audit

logger = logging.getLogger(__name__)

@swagger_auto_schema(
    method='post',
    tags=['Smart Query API'],
    operation_description="""
    Execute natural language database queries using AI
    
    **功能說明:**
    - 接收自然語言查詢，自動轉換為 SQL 並執行
    - 支援 MTB OPS 報表系統的各種查詢需求
    - 自動記錄查詢歷史和審計日誌
    
    **使用範例:**
    - "顯示所有 Production Line 的名稱"
    - "找出點擊率最高的 10 個報表"
    - "列出 HBM 產線下的所有 Function"
    - "統計每個 Function 的報表數量"
    
    **安全機制:**
    - 自動檢查 SQL 安全性，防止危險操作
    - 只允許 SELECT 查詢，禁止 INSERT/UPDATE/DELETE
    - 記錄所有查詢活動供審計使用
    """,
    operation_summary="自然語言資料庫查詢 API",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'query': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="自然語言查詢文本",
                example="顯示所有 Production Line 的名稱和描述"
            ),
            'session_id': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="聊天會話 ID，用於關聯查詢歷史",
                example="test-session-001"
            )
        },
        required=['query', 'session_id']
    ),
)
@api_view(['POST'])
@permission_classes([AllowAny])  # 改為 AllowAny 以便測試
def smart_query(request):
    """Handle smart query requests"""
    try:
        # 解析請求數據
        query_text = request.data.get('query', '').strip()
        session_id = request.data.get('session_id')
        
        if not query_text:
            return Response({
                'success': False,
                'error': 'Query text is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not session_id:
            return Response({
                'success': False,
                'error': 'Session ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 創建或獲取聊天會話
        chat_session, created = ChatSession.objects.using('MTBOI45').get_or_create(
            session_id=session_id,
            defaults={'session_title': f'Smart Query - {session_id[:8]}'}
        )
        
        # 創建資料庫感知的聊天服務
        db_service = DatabaseAwareChatService(session_id)
        
        # 執行查詢
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                db_service.process_database_query(query_text)
            )
        finally:
            loop.close()
        
        # 保存查詢記錄
        _save_query_message(chat_session, query_text, result)
        
        # 保存查詢記錄到查詢歷史
        query_history = _save_query_history(chat_session, query_text, result, request)
        
        # 記錄審計日誌
        if hasattr(request, 'user') and request.user.is_authenticated:
            log_query_audit(
                user=request.user,
                session_id=session_id,
                action='query_executed',
                resource='smart_query_api',
                details={
                    'query': query_text,
                    'success': result['success'],
                    'result_count': result.get('result_count', 0)
                },
                request=request
            )
            
        return Response({
            'success': result['success'],
            'data': {
                'query': query_text,
                'sql_query': result.get('sql_query', ''),
                'result': result.get('formatted_result', ''),
                'result_count': result.get('result_count', 0),
                'raw_data': result.get('raw_result', []),
                'query_history_id': str(query_history.query_id) if query_history else None
            },
            'message': result.get('message', ''),
            'error': result.get('error', None)
        })
        
    except Exception as e:
        logger.error(f"Smart query API error: {e}")
        return Response({
            'success': False,
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def _save_query_message(session: ChatSession, query: str, result: Dict):
    """Save query and result as chat messages"""
    try:
        # 保存用戶查詢
        ChatMessage.objects.using('MTBOI45').create(
            session=session,
            message_type='user',
            content=query,
            metadata={
                'query_type': 'smart_query',
                'is_database_query': True
            }
        )
        
        # 保存AI回應
        ChatMessage.objects.using('MTBOI45').create(
            session=session,
            message_type='ai',
            content=result.get('message', ''),
            metadata={
                'query_type': 'smart_query_response',
                'sql_query': result.get('sql_query', ''),
                'result_count': result.get('result_count', 0),
                'success': result.get('success', False)
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to save query message: {e}")

def _save_query_history(session: ChatSession, query: str, result: Dict, request) -> QueryHistory:
    """Save query to QueryHistory model"""
    try:
        # 計算執行時間 (如果有的話)
        execution_time = result.get('execution_time', None)
        
        query_history = QueryHistory.objects.using('MTBOI45').create(
            session=session,
            user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
            original_query=query,
            query_type='natural_language',
            generated_sql=result.get('sql_query', ''),
            status='success' if result['success'] else 'failed',
            result_count=result.get('result_count', 0),
            execution_time=execution_time,
            error_message=result.get('error', ''),
            metadata={
                'api_endpoint': 'smart_query_api',
                'formatted_result': result.get('formatted_result', ''),
                'raw_result_preview': str(result.get('raw_result', []))[:500]  # 只保存前500字符
            }
        )
        
        return query_history
        
    except Exception as e:
        logger.error(f"Failed to save query history: {e}")
        return None

@swagger_auto_schema(
    method='get',
    tags=['Smart Query API'],
    operation_description="獲取資料庫 Schema 信息，包含可查詢的表格和欄位",
    operation_summary="資料庫 Schema 信息 API",
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_schema_info(request):
    """Get database schema information"""
    try:
        db_service = DatabaseAwareChatService('temp_session')
        schema_info = db_service.get_schema_info()
        
        return Response({
            'success': True,
            'data': schema_info
        })
        
    except Exception as e:
        logger.error(f"Schema info API error: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(
    method='get',
    tags=['Smart Query API'],
    operation_description="獲取快速業務洞察，提供預設的重要指標和統計信息",
    operation_summary="快速業務洞察 API",
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_quick_insights(request):
    """Get quick business insights"""
    try:
        db_service = DatabaseAwareChatService('temp_session')
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            insights = loop.run_until_complete(db_service.get_quick_insights())
        finally:
            loop.close()
        
        return Response({
            'success': insights['success'],
            'data': insights.get('insights', {}),
            'error': insights.get('error', None)
        })
        
    except Exception as e:
        logger.error(f"Quick insights API error: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(
    method='post',
    tags=['Smart Query API'],
    operation_description="驗證 SQL 查詢的安全性，檢查是否包含危險操作",
    operation_summary="SQL 查詢安全驗證 API",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'sql_query': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="要驗證的 SQL 查詢",
                example="SELECT * FROM core_reportgroup WHERE group_name = 'HBM'"
            )
        },
        required=['sql_query']
    ),
)
@api_view(['POST'])
@permission_classes([AllowAny])
def validate_query(request):
    """Validate SQL query safety"""
    try:
        sql_query = request.data.get('sql_query', '').strip()
        
        if not sql_query:
            return Response({
                'success': False,
                'error': 'SQL query is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        schema_helper = DjangoSchemaHelper()
        is_safe, message = schema_helper.validate_query_safety(sql_query)
        
        return Response({
            'success': True,
            'data': {
                'is_safe': is_safe,
                'message': message,
                'sql_query': sql_query
            }
        })
        
    except Exception as e:
        logger.error(f"Query validation API error: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(
    method='get',
    tags=['Smart Query API'],
    operation_description="獲取建議的查詢範例，幫助用戶了解可以執行的查詢類型",
    operation_summary="查詢建議 API",
    manual_parameters=[
        openapi.Parameter(
            'category',
            openapi.IN_QUERY,
            description="過濾特定類別的建議",
            type=openapi.TYPE_STRING,
            enum=['basic', 'analytics', 'production', 'statistics', 'trends'],
            required=False
        )
    ],
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_query_suggestions(request):
    """Get suggested queries for users"""
    try:
        suggestions = [
            {
                'title': '顯示所有 Production Line',
                'description': '列出系統中所有的生產線',
                'query': '顯示所有 Production Line 的名稱',
                'category': 'basic'
            },
            {
                'title': '熱門報表排行',
                'description': '找出點擊率最高的報表',
                'query': '找出點擊率最高的 10 個報表',
                'category': 'analytics'
            },
            {
                'title': 'HBM 產線功能',
                'description': '查看 HBM 產線下的所有功能模組',
                'query': '列出 HBM 產線下的所有 Function',
                'category': 'production'
            },
            {
                'title': '報表使用統計',
                'description': '統計每個功能模組的報表數量',
                'query': '統計每個 Function 的報表數量',
                'category': 'statistics'
            },
            {
                'title': '未使用報表',
                'description': '找出從未被瀏覽的報表',
                'query': '找出從未被瀏覽的報表',
                'category': 'analytics'
            },
            {
                'title': '最近使用趨勢',
                'description': '分析最近一週的報表使用情況',
                'query': '分析最近一週的報表使用趨勢',
                'category': 'trends'
            }
        ]
        
        # 可以根據用戶權限或偏好過濾建議
        category_filter = request.GET.get('category')
        if category_filter:
            suggestions = [s for s in suggestions if s['category'] == category_filter]
        
        return Response({
            'success': True,
            'data': {
                'suggestions': suggestions,
                'categories': ['basic', 'analytics', 'production', 'statistics', 'trends']
            }
        })
        
    except Exception as e:
        logger.error(f"Query suggestions API error: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(
    method='get',
    tags=['Smart Query API'],
    operation_description="獲取指定會話的查詢歷史記錄",
    operation_summary="查詢歷史 API",
    manual_parameters=[
        openapi.Parameter(
            'session_id',
            openapi.IN_PATH,
            description="聊天會話 ID",
            type=openapi.TYPE_STRING,
            required=True
        )
    ],
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_query_history(request, session_id):
    """Get query history for a session"""
    try:
        # 獲取會話的查詢歷史
        messages = ChatMessage.objects.using('MTBOI45').filter(
            session__session_id=session_id,
            metadata__query_type__in=['smart_query', 'smart_query_response']
        ).order_by('-created_at')[:50]  # 最近50條記錄
        
        history = []
        current_query = None
        
        for message in reversed(messages):  # 反轉以正確配對
            if message.metadata.get('query_type') == 'smart_query':
                current_query = {
                    'id': message.id,
                    'query': message.content,
                    'timestamp': message.created_at.isoformat(),
                    'response': None
                }
            elif message.metadata.get('query_type') == 'smart_query_response' and current_query:
                current_query['response'] = {
                    'content': message.content,
                    'sql_query': message.metadata.get('sql_query', ''),
                    'result_count': message.metadata.get('result_count', 0),
                    'success': message.metadata.get('success', False)
                }
                history.append(current_query)
                current_query = None
        
        return Response({
            'success': True,
            'data': {
                'history': list(reversed(history)),  # 最新的在前
                'total_count': len(history)
            }
        })
        
    except Exception as e:
        logger.error(f"Query history API error: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)