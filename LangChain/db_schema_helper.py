from django.apps import apps
from typing import Dict, List, Optional
import json

class DjangoSchemaHelper:
    """Helper to extract Django model schema for LangChain"""
    
    def __init__(self, target_apps: List[str] = None):
        """
        Initialize schema helper
        
        Args:
            target_apps: List of Django app labels to include (default: ['core'])
        """
        self.target_apps = target_apps or ['core']
    
    def get_model_schema(self) -> Dict:
        """Extract schema information from Django models"""
        schema_info = {}
        
        for app_label in self.target_apps:
            try:
                app_config = apps.get_app_config(app_label)
                models = app_config.get_models()
                
                schema_info[app_label] = {}
                
                for model in models:
                    # 只處理 managed=True 的模型
                    if not model._meta.managed:
                        continue
                        
                    model_name = model.__name__
                    schema_info[app_label][model_name] = {
                        'table_name': model._meta.db_table,
                        'verbose_name': getattr(model._meta, 'verbose_name', model_name),
                        'fields': {},
                        'relationships': {},
                        'business_description': self._get_business_description(model_name)
                    }
                    
                    # 提取欄位資訊
                    for field in model._meta.fields:
                        field_info = {
                            'type': field.__class__.__name__,
                            'db_column': getattr(field, 'db_column', field.name),
                            'null': field.null,
                            'blank': field.blank,
                            'verbose_name': getattr(field, 'verbose_name', field.name),
                            'help_text': getattr(field, 'help_text', ''),
                            'max_length': getattr(field, 'max_length', None),
                            'choices': getattr(field, 'choices', None)
                        }
                        
                        # 處理外鍵關係
                        if hasattr(field, 'related_model') and field.related_model:
                            field_info['related_model'] = field.related_model.__name__
                            field_info['related_table'] = field.related_model._meta.db_table
                            
                            # 添加到關係字典
                            schema_info[app_label][model_name]['relationships'][field.name] = {
                                'type': 'ForeignKey',
                                'related_model': field.related_model.__name__,
                                'related_table': field.related_model._meta.db_table,
                                'on_delete': str(field.on_delete.__name__ if hasattr(field, 'on_delete') else 'CASCADE')
                            }
                        
                        schema_info[app_label][model_name]['fields'][field.name] = field_info
                    
                    # 處理反向關係 (Many-to-One, Many-to-Many)
                    for rel in model._meta.related_objects:
                        if rel.related_model._meta.app_label in self.target_apps:
                            rel_name = rel.get_accessor_name()
                            schema_info[app_label][model_name]['relationships'][rel_name] = {
                                'type': 'Reverse' + rel.__class__.__name__,
                                'related_model': rel.related_model.__name__,
                                'related_table': rel.related_model._meta.db_table,
                                'related_field': rel.field.name
                            }
            
            except Exception as e:
                print(f"Error processing app {app_label}: {e}")
        
        return schema_info
    
    def _get_business_description(self, model_name: str) -> str:
        """Get business description for models"""
        descriptions = {
            'ReportGroup': 'Production Line - 生產線群組，代表不同的製造產線',
            'ReportSubgroup': 'Function - 功能子群組，屬於特定生產線的功能模組',
            'Report': 'Report - 具體的報表項目，包含 URL 和相關資訊',
            'ReportTag': 'Tag - 報表標籤，用於分類和搜尋',
            'ReportMTGroup': 'MT Group - MT 群組分類，用於報表的進階分組',
            'ReportViewCount': 'View Count - 報表瀏覽次數記錄，追蹤用戶對報表的使用情況'
        }
        return descriptions.get(model_name, f'{model_name} - 業務模型')
    
    def get_django_table_names(self) -> List[str]:
        """獲取 Django models 對應的表格名稱"""
        table_names = []
        
        for app_label in self.target_apps:
            try:
                app_config = apps.get_app_config(app_label)
                models = app_config.get_models()
                
                for model in models:
                    db_table = model._meta.db_table
                
                    # 移除可能的方括號和 schema 前綴，只保留表格名稱
                    clean_table = db_table.replace('[', '').replace(']', '')
                    
                    table_names.append(clean_table)
                        
            except Exception as e:
                print(f"Error getting tables from app {app_label}: {e}")
        
        print(f"Total tables found: {len(table_names)}")
        print(f"Tables: {table_names}")
        
        return table_names
    
    def generate_schema_prompt(self, include_sample_queries: bool = True) -> str:
        """Generate a comprehensive prompt describing the database schema"""
        schema_info = self.get_model_schema()
        
        prompt_parts = [
            "=== MTB OPS 報表系統資料庫結構 ===\n",
            "這是一個製造業報表管理系統，包含以下核心業務模型：\n"
        ]
        
        for app_label, models in schema_info.items():
            prompt_parts.append(f"\n--- {app_label.upper()} APP ---")
            
            for model_name, model_info in models.items():
                prompt_parts.append(f"\n📋 {model_name} ({model_info['business_description']})")
                prompt_parts.append(f"   資料表: {model_info['table_name']}")
                
                # 重要欄位
                important_fields = []
                for field_name, field_info in model_info['fields'].items():
                    if field_name in ['id', 'name', 'title', 'url', 'sequence', 'created_at']:
                        field_desc = f"{field_name}"
                        if field_info.get('verbose_name'):
                            field_desc += f" ({field_info['verbose_name']})"
                        important_fields.append(field_desc)
                
                if important_fields:
                    prompt_parts.append(f"   主要欄位: {', '.join(important_fields)}")
                
                # 關聯關係
                if model_info['relationships']:
                    relations = []
                    for rel_name, rel_info in model_info['relationships'].items():
                        if rel_info['type'] == 'ForeignKey':
                            relations.append(f"{rel_name} -> {rel_info['related_model']}")
                    
                    if relations:
                        prompt_parts.append(f"   關聯: {', '.join(relations)}")
        
        # 業務邏輯說明
        prompt_parts.extend([
            "\n=== 業務邏輯層級關係 ===",
            "Production Line (ReportGroup) → Function (ReportSubgroup) → Report",
            "- 每個 Production Line 包含多個 Function",
            "- 每個 Function 包含多個 Report",
            "- Report 可以有多個 Tag 和 MT Group 分類",
            "- 系統會記錄每個 Report 的瀏覽次數 (view count)"
        ])
        
        if include_sample_queries:
            prompt_parts.extend([
                "\n=== 常見查詢範例 ===",
                "1. '顯示所有 Production Line 的名稱' - 查詢 ReportGroup",
                "2. '列出 HBM 產線下的所有 Function' - 關聯查詢 ReportGroup 和 ReportSubgroup", 
                "3. '找出點擊率最高的 10 個報表' - 關聯 Report 和 ReportViewCount，按瀏覽次數排序",
                "4. '顯示包含品質管理標籤的報表' - Report 和 ReportTag 的關聯查詢",
                "5. '統計每個 Function 的報表數量' - GROUP BY 統計查詢",
                "6. '分析最近一週的報表使用趨勢' - ReportViewCount 按時間統計",
                "7. '找出從未被瀏覽的報表' - Report LEFT JOIN ReportViewCount 查詢"
            ])
        
        return "\n".join(prompt_parts)
    
    def get_table_relationships_map(self) -> Dict[str, List[str]]:
        """獲取表格關聯關係映射，用於 SQL 查詢優化"""
        schema_info = self.get_model_schema()
        relationships = {}
        
        for app_label, models in schema_info.items():
            for model_name, model_info in models.items():
                table_name = model_info['table_name']
                related_tables = []
                
                for rel_name, rel_info in model_info['relationships'].items():
                    if rel_info['type'] == 'ForeignKey':
                        related_tables.append(rel_info['related_table'])
                
                relationships[table_name] = related_tables
        
        return relationships
    
    def validate_query_safety(self, sql_query: str) -> tuple[bool, str]:
        """驗證 SQL 查詢的安全性"""
        sql_upper = sql_query.upper().strip()
        
        # 只允許 SELECT 查詢
        if not sql_upper.startswith('SELECT'):
            return False, "只允許 SELECT 查詢"
        
        # 禁止的關鍵字
        forbidden_keywords = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 
            'TRUNCATE', 'EXEC', 'EXECUTE', 'DECLARE', 'CURSOR'
        ]
        
        for keyword in forbidden_keywords:
            if keyword in sql_upper:
                return False, f"禁止使用 {keyword} 關鍵字"
        
        # 檢查是否只查詢允許的表格
        allowed_tables = self.get_django_table_names()
        # 這裡可以添加更複雜的表格名稱檢查邏輯
        
        return True, "查詢安全"