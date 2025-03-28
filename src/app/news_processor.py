"""
Core NewsProcessor module that serves as a unified entry point for both CLI and Web interfaces.
This ensures that both interfaces use the same processing logic.
"""

import logging
import os
import uuid
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator

from src.agents.deepresearch_agent import DeepresearchAgent
from src.models.config import AppConfig
from src.models.response import ChatMessage, ChatResponse
from src.utils.formatters import format_report, generate_markdown, generate_html, create_image_from_text
import time

logger = logging.getLogger(__name__)

class NewsProcessor:
    """
    Core processor for tech news and research functionality.
    Used by both CLI and Web interfaces to ensure consistency.
    """
    
    def __init__(self, config: Optional[AppConfig] = None):
        """
        Initialize the NewsProcessor
        
        Args:
            config: Application configuration
        """
        self.config = config or AppConfig.from_env()
        self.reports_dir = os.path.join("data", "reports")
        os.makedirs(self.reports_dir, exist_ok=True)
    
    async def process_tech_news_stream(self, topic: str, include_platforms: Optional[List[str]] = None,
                                     session_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process technology news with streaming updates
        
        Args:
            topic: Main topic to research
            include_platforms: List of platforms to include in the search
            session_id: Optional session ID, will generate one if not provided
            
        Returns:
            AsyncGenerator[Dict[str, Any], None]: Stream of processing updates
        """
        if not session_id:
            session_id = str(uuid.uuid4())
            
        if not include_platforms:
            include_platforms = ["web_site"]
        
        start_time = datetime.now()
        report_id = str(uuid.uuid4())
        
        try:
            # Initial update
            yield {
                'status': 'started',
                'message': f"Processing request for topic: {topic}",
                'topic': topic,
                'report_id': report_id,
                'timestamp': datetime.now().isoformat()
            }
            
            agent = DeepresearchAgent(session_id=session_id)
            message = ChatMessage(
                message=topic,
                metadata={"platforms": include_platforms}
            )

            report = ""
            async for update in agent.process_stream(message):
                if isinstance(update, dict):
                    report += update["content"]
                elif isinstance(update, str):
                    report += update
                yield update
                
            duration = (datetime.now() - start_time).total_seconds()
            created_at = datetime.now().isoformat()
            yield {
                'status': 'completed',
                'message': f"Report generated for topic: {topic}",
                'topic': topic,
                'report_id': report_id,
                'duration': duration,
                'timestamp': created_at
            }

            cover_image_path = ""
            try:
                cover_image_path = await create_image_from_text(topic, f"{self.reports_dir}/images")
            except Exception as e:
                logger.error(f"生成报告封面图失败: {e}")

            markdown = generate_markdown(topic, report)
            html = generate_html(topic, report)

            report_data = {
                "id": report_id,
                "title": topic,
                "content": report,
                "markdown": markdown,
                "html": html,
                "cover_image": cover_image_path,
                "created_at": created_at,
                "duration": duration,
                "session_id": session_id
            }

            await self._save_report(report_data)

            logger.info(f"报告生成完成: {topic} (ID: {report_id})")
        except Exception as e:
            logger.error(f"Error in streaming tech news process: {e}", exc_info=True)
            yield {
                'status': 'error',
                'error': str(e),
                'topic': topic,
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a saved report by ID
        
        Args:
            report_id: Report ID to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Report data if found, None otherwise
        """
        report_path = os.path.join(self.reports_dir, f"{report_id}.json")
        if not os.path.exists(report_path):
            return None
            
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading report: {e}")
            return None
    
    async def list_reports(self, limit: int = 10, 
                         filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List saved reports
        
        Args:
            limit: Maximum number of reports to return
            filter_type: Optional filter by report type
            
        Returns:
            List[Dict[str, Any]]: List of report summaries
        """
        reports = []
        
        try:
            import json
            for filename in os.listdir(self.reports_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.reports_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        report = json.load(f)
                        
                        # Apply filter
                        if filter_type and report.get("type") != filter_type:
                            continue
                            
                        # Only include summary information
                        summary_report = {
                            "id": report.get("id"),
                            "title": report.get("topic", "Untitled"),
                            "type": report.get("type", "general"),
                            "created_at": report.get("created_at"),
                            "platforms": report.get("platforms", [])
                        }
                        
                        reports.append(summary_report)
                        
            # Sort by creation time
            reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            # Limit the number of results
            return reports[:limit]
            
        except Exception as e:
            logger.error(f"Error listing reports: {e}")
            return []
    
    async def delete_report(self, report_id: str) -> bool:
        """
        Delete a report
        
        Args:
            report_id: Report ID to delete
            
        Returns:
            bool: Whether deletion was successful
        """
        report_path = os.path.join(self.reports_dir, f"{report_id}.json")
        if not os.path.exists(report_path):
            return False
            
        try:
            os.remove(report_path)
            return True
        except Exception as e:
            logger.error(f"Error deleting report: {e}")
            return False
            
    async def _save_report(self, report: Dict[str, Any]) -> str:
        """
        Save a report to disk
        
        Args:
            report: Report data to save
            
        Returns:
            str: Path to the saved report
        """
        try:
            report_id = report.get('id')
            if not report_id:
                report_id = str(uuid.uuid4())
                report['id'] = report_id
                
            # Ensure the reports directory exists
            os.makedirs(self.reports_dir, exist_ok=True)
            
            # Save the report as json
            report_path = os.path.join(self.reports_dir, f"{report_id}.json")
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Report saved to: {report_path}")
            return report_path
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            
            # Try to save error information
            error_path = os.path.join(self.reports_dir, f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            try:
                with open(error_path, 'w', encoding='utf-8') as f:
                    json.dump({"error": str(e)}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
                
            return error_path