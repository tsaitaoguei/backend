from typing import Dict, List, Optional, Any
import logging
from django.conf import settings
from urllib.parse import quote_plus

# LangChain v0.3+ 新版本導入
from langchain_community.utilities import SQLDatabase
from langchain.chains.sql_database.query import create_sql_query_chain
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from .langchain_service import LangChainChatService
from .db_schema_helper import DjangoSchemaHelper
from helpers.DBHelper import SQLHelper

logger = logging.getLogger(__name__)

class DatabaseAwareChatService(LangChainChatService):
    """Enhanced chat service with database awareness for MTB OPS reports"""
    
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self.schema_helper = DjangoSchemaHelper(target_apps=['core'])
        self.db_helper = SQLHelper('MTBOI45')
        self.sql_database = None
        self.query_chain = None
        self._setup_database_connection()
    
    def _setup_database_connection(self):
        """Setup SQLDatabase connection for LangChain v0.3+"""
        try:
            # 從 Django settings 獲取資料庫配置
            db_config = settings.DATABASES['MTBOI45']
            
            # 構建 SQLAlchemy 連接字符串
            host = db_config['HOST']
            database = db_config['NAME']
            username = quote_plus(db_config['USER'])
            password = quote_plus(db_config['PASSWORD'])
            driver = quote_plus(db_config['OPTIONS']['driver'])
            
            connection_string = (
                f"mssql+pyodbc://{username}:{password}@{host}/{database}"
                f"?driver={driver}&MARS_Connection=yes"
            )
            
            # 直接使用 models 定義的表格名稱
            model_tables = self.schema_helper.get_django_table_names()
            
            logger.info(f"Model tables from Django: {model_tables}")
            
            # 創建 SQLDatabase 時只包含指定的表格
            self.sql_database = SQLDatabase.from_uri(
                database_uri=connection_string,
                include_tables=model_tables,
            )
            
            logger.info("SQLDatabase connection established successfully")
            logger.info(f"Available tables: {self.sql_database.get_usable_table_names()}")
            
        except Exception as e:
            logger.error(f"Failed to setup database connection: {e}")
            self.sql_database = None
    
    def _create_query_chain(self, llm=None):
        """Create SQL query chain using LangChain v0.3+ API with correct input variables"""
        if not self.sql_database:
            raise ValueError("Database connection not established")
        
        # 如果沒有傳入 llm，使用 self.llm
        if llm is None:
            llm = self.llm
        
        try:
            # 使用 LangChain 的默認 prompt，但不自定義
            # 這樣可以確保使用正確的輸入變數
            sql_query_chain = create_sql_query_chain(llm, self.sql_database)
            
            # 創建完整的執行鏈
            full_chain = (
                RunnablePassthrough.assign(query=sql_query_chain)
                | RunnablePassthrough.assign(
                    result=lambda x: self._execute_sql_safely(x["query"])
                )
            )
            
            return full_chain
            
        except Exception as e:
            logger.error(f"Failed to create query chain: {e}")
            raise ValueError(f"無法創建查詢鏈: {str(e)}")

    def _execute_sql_safely(self, sql_query: str):
        """安全執行 SQL 查詢"""
        try:
            # 清理 SQL 查詢（移除可能的 markdown 標記）
            if isinstance(sql_query, dict) and 'choices' in sql_query:
                sql_query = sql_query['choices'][0]['message']['content'].strip()
            
            if isinstance(sql_query, str):
                if sql_query.startswith('```sql'):
                    sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
                elif sql_query.startswith('```'):
                    sql_query = sql_query.replace('```', '').strip()
            
            # 驗證查詢安全性
            is_safe, safety_message = self.schema_helper.validate_query_safety(sql_query)
            if not is_safe:
                return f"安全檢查失敗: {safety_message}"
            
            # 執行查詢
            result = self.sql_database.run(sql_query)
            return result
            
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return f"查詢執行錯誤: {str(e)}"
    
    async def process_database_query(self, user_message: str, context: Dict = None) -> Dict[str, Any]:
        """Process natural language database query using LangChain v0.3+"""
        try:
            if not self.sql_database:
                return {
                    'success': False,
                    'error': '資料庫連接未建立',
                    'message': '抱歉，目前無法執行資料庫查詢。請聯繫系統管理員。'
                }
            
            # 創建查詢鏈
            if not self.query_chain:
                self.query_chain = self._create_query_chain()
            
            # 執行查詢
            logger.info(f"Processing database query: {user_message}")
            
            # 使用正確的輸入格式調用 invoke 方法
            # LangChain 的默認 prompt 期望 'question' 作為輸入
            result = self.query_chain.invoke({
                "question": user_message
            })
            
            sql_query = result.get('query', '')
            query_result = result.get('result', '')
            
            # 驗證查詢安全性
            is_safe, safety_message = self.schema_helper.validate_query_safety(sql_query)
            
            if not is_safe:
                return {
                    'success': False,
                    'error': f'查詢安全檢查失敗: {safety_message}',
                    'message': '抱歉，這個查詢不符合安全要求。'
                }
            
            # 處理查詢結果
            if isinstance(query_result, str) and "錯誤" in query_result:
                return {
                    'success': False,
                    'error': query_result,
                    'message': f'查詢執行失敗：{query_result}'
                }
            
            # 解析結果為列表格式
            parsed_result = self._parse_sql_result(query_result)
            
            # 格式化結果
            formatted_result = self._format_query_result(parsed_result, user_message)
            
            # 記錄查詢日誌
            await self._log_database_query(user_message, sql_query, len(parsed_result) if isinstance(parsed_result, list) else 1)
            
            return {
                'success': True,
                'sql_query': sql_query,
                'raw_result': parsed_result,
                'formatted_result': formatted_result,
                'message': formatted_result,
                'result_count': len(parsed_result) if isinstance(parsed_result, list) else 1
            }
            
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'查詢執行時發生錯誤：{str(e)}'
            }
    
    def _parse_sql_result(self, result_string: str) -> List:
        """Parse SQL result string into list format"""
        if not result_string or result_string.strip() == "":
            return []
        
        try:
            # 如果結果是字符串格式，嘗試解析為行
            lines = result_string.strip().split('\n')
            parsed_result = []
            
            for line in lines:
                if line.strip():
                    # 嘗試按分隔符分割（可能是 tab 或多個空格）
                    if '\t' in line:
                        row = line.split('\t')
                    elif '|' in line:
                        row = [col.strip() for col in line.split('|')]
                    else:
                        # 按多個空格分割
                        row = [col.strip() for col in line.split() if col.strip()]
                    
                    if len(row) == 1:
                        parsed_result.append(row[0])
                    else:
                        parsed_result.append(tuple(row))
            
            return parsed_result if parsed_result else [result_string]
            
        except Exception as e:
            logger.error(f"Failed to parse SQL result: {e}")
            return [result_string]
    
    def _format_query_result(self, query_result: List, original_question: str) -> str:
        """Format query result for user display"""
        if not query_result:
            return "查詢完成，但沒有找到符合條件的資料。"
        
        # 如果結果是字符串，直接返回
        if isinstance(query_result, str):
            return query_result
        
        # 如果是列表但只有一個元素且是字符串
        if len(query_result) == 1 and isinstance(query_result[0], str):
            return query_result[0]
        
        # 格式化表格數據
        if isinstance(query_result, list) and len(query_result) > 0:
            formatted_lines = [f"📊 查詢結果（共 {len(query_result)} 筆資料）：\n"]
            
            for i, row in enumerate(query_result[:10], 1):  # 限制顯示前10筆
                if isinstance(row, (tuple, list)):
                    row_str = " | ".join(str(item) for item in row)
                    formatted_lines.append(f"{i:2d}. {row_str}")
                else:
                    formatted_lines.append(f"{i:2d}. {str(row)}")
            
            if len(query_result) > 10:
                formatted_lines.append(f"\n... 還有 {len(query_result) - 10} 筆資料")
            
            return "\n".join(formatted_lines)
        
        return str(query_result)
    
    async def _log_database_query(self, question: str, sql_query: str, result_count: int):
        """Log database query for audit purposes"""
        try:
            log_data = {
                'session_id': self.session_id,
                'question': question,
                'sql_query': sql_query,
                'result_count': result_count,
                'timestamp': 'NOW()'
            }
            
            logger.info(f"Database query logged: {log_data}")
            
        except Exception as e:
            logger.error(f"Failed to log database query: {e}")
    
    async def get_quick_insights(self) -> Dict[str, Any]:
        """Get quick business insights from the database"""
        try:
            insights = {}
            
            # 總計統計
            total_reports = await self._execute_simple_query(
                "SELECT COUNT(*) FROM core_report"
            )
            total_groups = await self._execute_simple_query(
                "SELECT COUNT(*) FROM core_reportgroup"
            )
            total_subgroups = await self._execute_simple_query(
                "SELECT COUNT(*) FROM core_reportsubgroup"
            )
            
            insights['totals'] = {
                'reports': total_reports or 0,
                'production_lines': total_groups or 0,
                'functions': total_subgroups or 0
            }
            
            # 熱門報表（如果有 view count 資料）
            popular_reports_query = """
                SELECT TOP 5 r.report_name, ISNULL(COUNT(v.ReportOID), 0) as view_count
                FROM core_report r
                LEFT JOIN core_reportviewcount v ON r.report_oid = v.ReportOID
                GROUP BY r.report_name, r.report_oid
                ORDER BY view_count DESC
            """
            
            popular_reports = await self._execute_simple_query(popular_reports_query)
            insights['popular_reports'] = popular_reports or []
            
            return {
                'success': True,
                'insights': insights
            }
            
        except Exception as e:
            logger.error(f"Failed to get quick insights: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _execute_simple_query(self, sql_query: str):
        """Execute a simple SQL query and return result"""
        try:
            # 驗證查詢安全性
            is_safe, safety_message = self.schema_helper.validate_query_safety(sql_query)
            if not is_safe:
                raise ValueError(f"Unsafe query: {safety_message}")
            
            # 使用 DBHelper 執行查詢
            result = self.db_helper.execute_query(sql_query)
            
            if result and len(result) > 0:
                if len(result) == 1 and len(result[0]) == 1:
                    return result[0][0]  # 單一值
                else:
                    return result  # 多列結果
            
            return None
            
        except Exception as e:
            logger.error(f"Simple query execution failed: {e}")
            return None
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get database schema information"""
        return {
            'models': self.schema_helper.get_model_schema(),
            'tables': self.schema_helper.get_django_table_names(),
            'relationships': self.schema_helper.get_table_relationships_map(),
            'description': self.schema_helper.generate_schema_prompt()
        }
    
    async def suggest_queries(self, context: str = "") -> List[str]:
        """Suggest relevant queries based on context"""
        suggestions = [
            "顯示所有 Production Line",
            "列出最熱門的 5 個報表",
            "統計每個功能模組的報表數量",
            "找出從未被瀏覽的報表",
            "顯示所有報表群組和描述"
        ]
        
        # 可以根據 context 動態調整建議
        if "hbm" in context.lower():
            suggestions.insert(0, "顯示 HBM 相關的所有報表")
        
        return suggestions
    
    # 在 DatabaseAwareChatService 類別的最後添加這個測試方法
    def quick_sql_test(self, question: str) -> str:
        """
        快速測試單一問題的 SQL 生成和執行
        
        Args:
            question: 自然語言問題
            
        Returns:
            str: 格式化的測試結果
        """
        try:
            if not self.sql_database:
                return "❌ 資料庫未連接"
            
            # 使用 LangChain 生成 SQL
            from langchain.chains.sql_database.query import create_sql_query_chain
            sql_chain = create_sql_query_chain(self.llm, self.sql_database)
            
            # 生成 SQL
            generated_sql = sql_chain.invoke({"question": question})
            
            # 清理 SQL
            cleaned_sql = self._clean_sql_response(generated_sql)
            
            if not cleaned_sql:
                return f"❌ AI 無法生成有效的 SQL\n原始回應: {str(generated_sql)[:100]}..."
            
            # 安全檢查
            is_safe, safety_message = self.schema_helper.validate_query_safety(cleaned_sql)
            
            result_lines = [
                f"📝 問題: {question}",
                f"🔧 生成的 SQL: {cleaned_sql}",
                f"🔒 安全檢查: {'✅ 通過' if is_safe else '❌ 失敗'} - {safety_message}"
            ]
            
            # 如果安全，執行查詢
            if is_safe:
                try:
                    execution_result = self.sql_database.run(cleaned_sql)
                    result_preview = str(execution_result)[:200] + "..." if len(str(execution_result)) > 200 else str(execution_result)
                    result_lines.append(f"🎯 執行結果: {result_preview}")
                except Exception as exec_error:
                    result_lines.append(f"⚠️ 執行錯誤: {str(exec_error)}")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            return f"❌ 測試失敗: {str(e)}"

    def test_database_connection(self) -> Dict[str, Any]:
        """
        測試資料庫連接和基本功能
        
        Returns:
            Dict: 測試結果
        """
        results = {
            'database_connected': False,
            'ai_service_working': False,
            'available_tables': [],
            'test_queries': []
        }
        
        # 檢查資料庫連接
        if self.sql_database:
            results['database_connected'] = True
            try:
                results['available_tables'] = self.schema_helper.get_django_table_names()
            except Exception as e:
                results['available_tables'] = [f"Error getting tables: {e}"]
        
        # 檢查 AI 服務
        try:
            test_response = self.llm.invoke("Say hello")
            if hasattr(test_response, 'content'):
                content = test_response.content
            else:
                content = str(test_response)
            
            if content and len(content.strip()) > 5 and "Sorry" not in content:
                results['ai_service_working'] = True
        except Exception as e:
            results['ai_service_working'] = False
        
        # 如果都正常，測試幾個簡單查詢
        if results['database_connected'] and results['ai_service_working']:
            simple_tests = [
                "SELECT COUNT(*) FROM core_report",
                "SELECT TOP 3 group_name FROM core_reportgroup",
                "SELECT COUNT(*) FROM core_reportsubgroup"
            ]
            
            for sql in simple_tests:
                try:
                    is_safe, _ = self.schema_helper.validate_query_safety(sql)
                    if is_safe:
                        result = self.sql_database.run(sql)
                        results['test_queries'].append({
                            'sql': sql,
                            'success': True,
                            'result': str(result)[:100]
                        })
                    else:
                        results['test_queries'].append({
                            'sql': sql,
                            'success': False,
                            'result': 'Safety check failed'
                        })
                except Exception as e:
                    results['test_queries'].append({
                        'sql': sql,
                        'success': False,
                        'result': str(e)
                    })
        
        return results
    
    
def test_database_connection_detailed(self) -> Dict[str, Any]:
    """詳細的資料庫連接測試 (簡化版)"""
    results = {
        'connection_string_built': False,
        'sqlalchemy_connection': False,
        'langchain_database': False,
        'model_tables': [],
        'available_tables': [],
        'matching_tables': [],
        'errors': []
    }
    
    try:
        # 1. 測試連接字符串構建
        db_config = settings.DATABASES['MTBOI45']
        host = db_config['HOST']
        database = db_config['NAME']
        username = quote_plus(db_config['USER'])
        password = quote_plus(db_config['PASSWORD'])
        driver = quote_plus(db_config['OPTIONS']['driver'])
        
        connection_string = (
            f"mssql+pyodbc://{username}:{password}@{host}/{database}"
            f"?driver={driver}&MARS_Connection=yes"
        )
        results['connection_string_built'] = True
        
        # 2. 測試 SQLAlchemy 連接
        from sqlalchemy import create_engine, text
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            results['sqlalchemy_connection'] = True
        
        # 3. 測試 LangChain SQLDatabase
        from langchain_community.utilities import SQLDatabase
        sql_db = SQLDatabase.from_uri(connection_string, sample_rows_in_table_info=1)
        results['langchain_database'] = True
        
        # 4. 獲取我們的 model 表格
        model_tables = self.schema_helper.get_django_table_names()
        results['model_tables'] = model_tables
        
        # 5. 獲取資料庫中可用的表格
        available_tables = sql_db.get_usable_table_names()
        results['available_tables'] = available_tables
        
        # 6. 找出匹配的表格
        matching_tables = []
        for model_table in model_tables:
            clean_model_table = model_table.replace('[', '').replace(']', '')
            for db_table in available_tables:
                if clean_model_table.lower().replace('.', '') in db_table.lower().replace('.', ''):
                    matching_tables.append({
                        'model': model_table,
                        'database': db_table
                    })
                    break
        
        results['matching_tables'] = matching_tables
        
    except Exception as e:
        results['errors'].append(str(e))
    
    return results