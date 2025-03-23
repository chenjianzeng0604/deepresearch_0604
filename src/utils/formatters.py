import logging
import os
import uuid
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io

logger = logging.getLogger(__name__)

def format_report(title: str, content: str, report_type: str = "comprehensive") -> Dict[str, Any]:
    """
    格式化报告内容为统一结构
    
    Args:
        title: 报告标题
        content: 报告内容
        report_type: 报告类型
        
    Returns:
        Dict[str, Any]: 格式化的报告数据
    """
    # 确保content是字符串
    if not isinstance(content, str):
        content = str(content)
    
    # 提取摘要（使用内容的前200个字符作为摘要）
    summary = content[:200].strip()
    if len(content) > 200:
        summary += "..."
    
    # 构建格式化的报告
    formatted = {
        "title": title,
        "content": content,
        "summary": summary,
        "type": report_type,
        "timestamp": datetime.now().isoformat(),
        "word_count": len(content)
    }
    
    return formatted

def generate_markdown(title: str, content: str) -> str:
    """
    将报告内容生成Markdown格式
    
    Args:
        title: 报告标题
        content: 报告内容
        
    Returns:
        str: Markdown格式的内容
    """
    # 添加标题
    markdown = f"# {title}\n\n"
    
    # 添加生成时间
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    markdown += f"*生成时间: {now}*\n\n"
    
    # 添加分隔线
    markdown += "---\n\n"
    
    # 添加内容
    markdown += content
    
    # 添加脚注
    markdown += "\n\n---\n\n*本报告由深度研究助手自动生成*"
    
    return markdown

def generate_html(title: str, content: str) -> str:
    """
    将报告内容生成HTML格式
    
    Args:
        title: 报告标题
        content: 报告内容
        
    Returns:
        str: HTML格式的内容
    """
    # 构建HTML模板
    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            line-height: 1.6;
            margin: 0 auto;
            max-width: 900px;
            padding: 20px;
            color: #333;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #3498db;
            margin-top: 30px;
        }}
        h3 {{
            color: #2980b9;
        }}
        .meta {{
            color: #7f8c8d;
            font-size: 0.9em;
            margin-bottom: 30px;
        }}
        .content {{
            text-align: justify;
        }}
        .footer {{
            margin-top: 50px;
            border-top: 1px solid #eee;
            padding-top: 20px;
            font-size: 0.8em;
            color: #7f8c8d;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">生成时间: {date}</div>
    <div class="content">
        {content_html}
    </div>
    <div class="footer">
        <p>本报告由深度研究助手自动生成</p>
    </div>
</body>
</html>
"""
    # 准备日期和处理内容
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    processed_content = content.replace("\n", "<br>")
    
    # 填充模板
    html = html_template.format(
        title=title,
        date=current_date,
        content_html=processed_content
    )
    
    return html

async def create_image_from_text(text: str, output_dir: str = "data/images") -> str:
    """
    从文本创建封面图片
    
    Args:
        text: 文本内容
        output_dir: 输出目录
        
    Returns:
        str: 图片文件路径
    """
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建图片
    width, height = 800, 400
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    
    try:
        # 设置字体
        try:
            # 尝试加载微软雅黑字体
            font = ImageFont.truetype("msyh.ttc", 32)
            small_font = ImageFont.truetype("msyh.ttc", 24)
        except Exception:
            # 使用默认字体
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        draw = ImageDraw.Draw(image)
        
        # 绘制背景
        for i in range(height):
            r = int(220 + i * 35 / height)
            g = int(230 + i * 25 / height)
            b = int(240 + i * 15 / height)
            draw.line([(0, i), (width, i)], fill=(r, g, b), width=1)
        
        # 绘制标题
        # 如果文本太长，添加换行
        if len(text) > 20:
            words = text.split()
            lines = []
            current_line = []
            
            for word in words:
                current_line.append(word)
                if len(" ".join(current_line)) > 20:
                    if len(current_line) > 1:
                        current_line.pop()
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        lines.append(" ".join(current_line))
                        current_line = []
            
            if current_line:
                lines.append(" ".join(current_line))
                
            y_offset = height // 2 - len(lines) * 20
            for line in lines:
                text_width = draw.textlength(line, font=font)
                x_position = (width - text_width) // 2
                draw.text((x_position, y_offset), line, fill=(33, 33, 33), font=font)
                y_offset += 50
        else:
            text_width = draw.textlength(text, font=font)
            x_position = (width - text_width) // 2
            draw.text((x_position, height // 2 - 16), text, fill=(33, 33, 33), font=font)
        
        # 绘制小文本
        footer_text = "深度研究报告"
        small_text_width = draw.textlength(footer_text, font=small_font)
        draw.text(((width - small_text_width) // 2, height - 50), footer_text, fill=(100, 100, 100), font=small_font)
        
        # 生成随机文件名
        filename = f"{uuid.uuid4()}.png"
        file_path = os.path.join(output_dir, filename)
        
        # 保存图片
        image.save(file_path)
        
        return file_path
        
    except Exception as e:
        logger.error(f"创建图片失败: {e}")
        return ""
