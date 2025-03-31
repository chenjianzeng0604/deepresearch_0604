"""
嵌入模型管理模块
负责管理和加载嵌入模型，避免重复加载
"""
import logging
import os
from typing import List, Dict, Any, Optional
from pymilvus.model.hybrid import BGEM3EmbeddingFunction
from huggingface_hub import snapshot_download

logger = logging.getLogger(__name__)

class EmbeddingModelManager:
    """
    嵌入模型管理器 - 单例模式实现
    确保整个应用只加载一次嵌入模型
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super(EmbeddingModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化嵌入模型管理器"""
        if self._initialized:
            return
        self.embedding_model = None
        self._setup_environment()
        self._init_embedding_model()
        self._initialized = True
    
    def _setup_environment(self):
        """设置环境变量"""
        os.environ["HTTP_PROXY"] = ""
        os.environ["HTTPS_PROXY"] = ""
        os.environ["http_proxy"] = ""
        os.environ["https_proxy"] = ""
        os.environ["NO_PROXY"] = "*"
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "local_models")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["HF_HOME"] = cache_dir
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    
    def _init_embedding_model(self):
        """初始化并下载嵌入模型"""
        try:
            model_name = "BAAI/bge-m3"
            cache_dir = os.environ.get("HF_HOME")
            
            logger.info(f"开始加载模型 {model_name} 从 {cache_dir}")
            
            try:
                model_path = snapshot_download(
                    repo_id=model_name,
                    cache_dir=cache_dir,
                    local_files_only=True,
                    token=os.environ.get('HF_TOKEN')
                )
                logger.info(f"模型已从本地加载: {model_path}")
            except Exception as e:
                logger.warning(f"本地模型不存在，尝试下载: {str(e)}")
                model_path = model_name
            
            self.embedding_model = BGEM3EmbeddingFunction(
                model_name=model_path,
                device="cpu",
                use_fp16=False
            )
            logger.info("成功加载BGE-M3模型")
        except Exception as e:
            logger.error(f"初始化嵌入模型失败: {str(e)}")
            self.embedding_model = None
    
    def generate_embeddings(self, texts: List[str]) -> List[Any]:
        """
        生成文本嵌入向量
        
        Args:
            texts: 文本列表
            
        Returns:
            List[Any]: 嵌入向量
        """
        if self.embedding_model is None:
            logger.warning("嵌入模型未初始化，尝试重新初始化")
            self._init_embedding_model()
            if self.embedding_model is None:
                logger.error("嵌入模型初始化失败，返回零向量")
                return [[0.0] * 1024]
        
        # 空文本列表处理
        if not texts or len(texts) == 0:
            logger.warning("收到空文本列表，返回零向量")
            return [[0.0] * 1024]
        
        # 过滤空文本
        valid_texts = [text for text in texts if text and len(text.strip()) > 0]
        if not valid_texts:
            logger.warning("所有文本都为空，返回零向量")
            return [[0.0] * 1024]
        
        # 添加重试机制
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                docs_embeddings = self.embedding_model._encode(valid_texts)
                return docs_embeddings['dense']
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"生成嵌入向量失败 (尝试 {attempt+1}/{max_retries}): {str(e)}，{retry_delay}秒后重试")
                    import time
                    time.sleep(retry_delay)
                    # 如果失败后尝试重新初始化模型
                    if attempt == 1:  # 第二次失败后重新初始化模型
                        logger.info("尝试重新初始化嵌入模型")
                        self._init_embedding_model()
                else:
                    logger.error(f"生成嵌入向量失败，已达最大重试次数: {str(e)}")
        
        # 所有重试都失败后返回零向量
        logger.error("所有嵌入向量生成尝试均失败，返回零向量")
        return [[0.0] * 1024 for _ in valid_texts]

embedding_manager = EmbeddingModelManager()
