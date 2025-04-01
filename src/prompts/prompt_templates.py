"""提示词模板管理模块
这个模块集中管理所有与LLM交互的提示词模板，便于统一维护和更新。
"""
# 集中管理所有提示词模板
PROMPT_TEMPLATES = {
    # 系统消息
    "DEFAULT_SYSTEM_MESSAGE": "You are a helpful assistant.",
    
    # 深度分析提示词
    "DEEP_ANALYSIS_TEMPLATE": """  
    针对用户问题，结合查到的数据和历史对话，进行深度总结。 
    
    当前时间：{current_time}

    用户问题：{query}

    查到的数据：{summaries}
    
    历史对话上下文：{context}
    
    你的深度总结：
    """,
    
    # 信息充分性评估提示词
    "EVALUATE_INFORMATION_TEMPLATE": """
    作为智能研究助手，你的任务是评估我们目前收集的信息是否足够回答用户的查询，不够的话反思下一步如何收集信息解决用户的查询，给出包含搜索关键字的搜索URL，并且给出反思的思考过程和结论。

    当前时间：{current_time}

    用户查询：{query}

    已收集的信息:
    {context_text}
    
    以JSON格式输出：
    1 enough字段：存放是否足够结果，足够值为True，不够值为False
    2 search_url：进一步搜索URL，一个或多个的数组结构，保证搜索可用，实用主义
    3 thought：反思的思考过程和结论，用自然语言方式输出方便用户阅读

    你的评估与反思:
    """,
    
    # 意图识别提示词
    "INTENT_RECOGNITION_TEMPLATE": """
    作为智能研究助手，你的任务是分析用户查询，并判断该查询最适合的研究领域。

    当前时间：{current_time}

    用户查询: {query}

    请分析该查询内容，判断其最匹配的专业领域类别。可选的领域有：
    - general：通用信息查询，没有明确属于特定领域
    - ai：人工智能、机器学习、深度学习、大模型等AI相关技术
    - healthcare：医疗健康、生物技术、药物研发等医疗领域

    请仅回复最匹配的领域名称（例如: "ai"），不要包含任何解释或其他文本。
    如果查询明显跨越多个领域或无法确定，请回复"general"。
    """,

    # 文章质量处理提示词
    "ARTICLE_QUALITY_TEMPLATE": """
    你是智能内容处理专家，帮我对爬取到的文章内容进行内容质量评估、智能压缩和主题提炼，最终结果以json格式输出，具体规则如下：
    1 先判断内容是否优质，将结果添加到high_quality字段(高质量值为True、低质量值为False)，不优质直接结束
    2 如果内容优质，判断字数是否超过{word_count}字需要压缩，将结果添加到compress字段(需压缩值为True、不需压缩值为False)
    3 如果优质文章需要压缩，把文章压缩结果放到compressed_article字段，压缩需保留原文不要加入自己的总结，尽可能打满{word_count}字避免语义严重缺失
    4 如果内容优质，提取文章主题放在title字段，内容不超过20字
    5 不要输出json格式以外的文本

    以下是文章内容：
    {article}
    """
}

from datetime import datetime

class PromptTemplates:
    """提示词模板类，集中管理所有提示词"""
    @classmethod
    def get_system_message(cls) -> str:
        """获取系统消息
        
        Returns:
            str: 系统消息
        """
        return PROMPT_TEMPLATES["DEFAULT_SYSTEM_MESSAGE"]
    
    @classmethod
    def format_deep_analysis_prompt(cls, query: str, summaries: str, context: str = "") -> str:
        """格式化深度分析提示词
        
        Args:
            query: 用户查询
            summaries: 摘要内容
            context: 历史对话上下文，默认为空字符串
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["DEEP_ANALYSIS_TEMPLATE"].format(
            query=query, 
            summaries=summaries, 
            context=context,
            current_time=datetime.now().strftime("%Y-%m-%d")
        )
    
    @classmethod
    def format_evaluate_information_prompt(cls, query: str, context_text: str) -> str:
        """格式化信息充分性评估提示词
        
        Args:
            query: 用户查询
            context_text: 已收集的信息文本
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["EVALUATE_INFORMATION_TEMPLATE"].format(query=query, context_text=context_text, current_time=datetime.now().strftime("%Y-%m-%d"))
        
    @classmethod
    def format_intent_recognition_prompt(cls, query: str) -> str:
        """格式化意图识别提示词
        
        Args:
            query: 用户查询
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["INTENT_RECOGNITION_TEMPLATE"].format(query=query, current_time=datetime.now().strftime("%Y-%m-%d"))

    @classmethod
    def format_article_quality_prompt(cls, article: str, word_count: int = 5000) -> str:
        """格式化文章质量评估提示词
        
        Args:
            article: 文章内容
            word_count: 文章字数
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["ARTICLE_QUALITY_TEMPLATE"].format(article=article, word_count=word_count)