import os
import logging
import shutil
import uuid
from typing import Optional
from pathlib import Path
import datetime

# 尝试导入文件处理相关库
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import docx2txt
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from fastapi import UploadFile

logger = logging.getLogger(__name__)

# 支持的文件类型及其处理函数映射
FILE_TYPE_HANDLERS = {
    ".pdf": "extract_text_from_pdf",
    ".doc": "extract_text_from_doc",
    ".docx": "extract_text_from_docx",
    ".txt": "extract_text_from_txt",
    ".md": "extract_text_from_txt",
    ".csv": "extract_text_from_txt",
}

async def save_uploaded_file(file: UploadFile, session_id: Optional[str] = None) -> str:
    """
    保存上传的文件
    
    Args:
        file: 上传的文件
        session_id: 会话ID，用于区分不同用户上传的文件
        
    Returns:
        str: 保存的文件路径
    """
    try:
        # 创建上传目录，如果提供了session_id则创建会话专属目录
        base_upload_dir = "data/uploads"
        if session_id:
            # 安全处理session_id，避免路径遍历攻击
            safe_session_id = session_id.replace(':', '_').replace('/', '_').replace('..', '_')
            upload_dir = os.path.join(base_upload_dir, safe_session_id)
        else:
            # 如果没有会话ID，则使用时间戳创建唯一目录
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            upload_dir = os.path.join(base_upload_dir, f"anonymous_{timestamp}")
        
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成唯一文件名，保留原始扩展名
        original_filename = file.filename
        if not original_filename:
            original_filename = "unknown_file"
        
        filename, extension = os.path.splitext(original_filename)
        unique_filename = f"{filename}_{uuid.uuid4().hex}{extension}"
        
        # 构建保存路径
        file_path = os.path.join(upload_dir, unique_filename)
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            contents = await file.read()
            buffer.write(contents)
        
        # 关闭文件
        await file.close()
        
        logger.info(f"文件已保存: {file_path}")
        return file_path
    
    except Exception as e:
        logger.error(f"保存文件时出错: {e}", exc_info=True)
        raise

async def process_document(file_path: str) -> bool:
    """
    处理文档，提取文本并进行预处理
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return False
        
        # 提取文本
        text = extract_text_from_file(file_path)
        if not text:
            logger.warning(f"无法从文件中提取文本: {file_path}")
            return False
        
        # 保存提取的文本
        text_file_path = f"{file_path}.txt"
        with open(text_file_path, "w", encoding="utf-8") as f:
            f.write(text)
        
        logger.info(f"文件处理完成: {file_path}")
        return True
    
    except Exception as e:
        logger.error(f"处理文档时出错: {e}", exc_info=True)
        return False

def extract_text_from_file(file_path: str) -> Optional[str]:
    """
    从文件中提取文本
    
    Args:
        file_path: 文件路径
        
    Returns:
        Optional[str]: 提取的文本，失败则返回None
    """
    try:
        # 获取文件扩展名
        _, extension = os.path.splitext(file_path)
        extension = extension.lower()
        
        # 根据文件类型调用相应的处理函数
        handler_name = FILE_TYPE_HANDLERS.get(extension)
        if handler_name and hasattr(globals()[handler_name], "__call__"):
            handler = globals()[handler_name]
            return handler(file_path)
        
        # 不支持的文件类型
        logger.warning(f"不支持的文件类型: {extension}")
        return None
    
    except Exception as e:
        logger.error(f"提取文本时出错: {e}", exc_info=True)
        return None

def extract_text_from_pdf(file_path: str) -> Optional[str]:
    """
    从PDF文件中提取文本
    
    Args:
        file_path: PDF文件路径
        
    Returns:
        Optional[str]: 提取的文本，失败则返回None
    """
    if not PDF_AVAILABLE:
        logger.error("无法提取PDF文本，缺少PyPDF2库")
        return None
    
    try:
        text = ""
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # 提取每一页的文本
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n\n"
        
        # 如果提取的文本为空，可能是扫描PDF
        if not text.strip():
            logger.warning(f"PDF文本提取为空，可能是扫描PDF: {file_path}")
            return f"[无法提取文本，可能是扫描PDF: {os.path.basename(file_path)}]"
        
        return text
    
    except Exception as e:
        logger.error(f"提取PDF文本时出错: {e}", exc_info=True)
        return None

def extract_text_from_docx(file_path: str) -> Optional[str]:
    """
    从DOCX文件中提取文本
    
    Args:
        file_path: DOCX文件路径
        
    Returns:
        Optional[str]: 提取的文本，失败则返回None
    """
    if not DOCX_AVAILABLE:
        logger.error("无法提取DOCX文本，缺少docx2txt库")
        return None
    
    try:
        # 使用docx2txt提取文本
        text = docx2txt.process(file_path)
        return text
    
    except Exception as e:
        logger.error(f"提取DOCX文本时出错: {e}", exc_info=True)
        return None

def extract_text_from_doc(file_path: str) -> Optional[str]:
    """
    从DOC文件中提取文本（需要外部转换）
    
    Args:
        file_path: DOC文件路径
        
    Returns:
        Optional[str]: 提取的文本，失败则返回None
    """
    try:
        # 目前没有纯Python的doc提取库，返回提示信息
        logger.warning(f"不支持直接提取DOC文件: {file_path}")
        return f"[DOC格式文件: {os.path.basename(file_path)} - 建议转换为DOCX格式]"
    
    except Exception as e:
        logger.error(f"处理DOC文件时出错: {e}", exc_info=True)
        return None

def extract_text_from_txt(file_path: str) -> Optional[str]:
    """
    从文本文件中提取文本
    
    Args:
        file_path: 文本文件路径
        
    Returns:
        Optional[str]: 提取的文本，失败则返回None
    """
    try:
        # 尝试不同编码打开文件
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                continue
        
        # 如果所有编码都失败，尝试二进制读取并解码
        with open(file_path, 'rb') as file:
            content = file.read()
            return content.decode('utf-8', errors='replace')
    
    except Exception as e:
        logger.error(f"提取文本文件内容时出错: {e}", exc_info=True)
        return None

def get_file_info(file_path: str) -> dict:
    """
    获取文件信息
    
    Args:
        file_path: 文件路径
        
    Returns:
        dict: 文件信息字典
    """
    try:
        path = Path(file_path)
        stats = path.stat()
        
        return {
            "filename": path.name,
            "path": str(path),
            "size": stats.st_size,
            "created": datetime.datetime.fromtimestamp(stats.st_ctime).isoformat(),
            "modified": datetime.datetime.fromtimestamp(stats.st_mtime).isoformat(),
            "extension": path.suffix.lower(),
        }
    
    except Exception as e:
        logger.error(f"获取文件信息时出错: {e}", exc_info=True)
        return {
            "filename": os.path.basename(file_path),
            "path": file_path,
            "error": str(e)
        }
