"""提示词模板管理模块
这个模块集中管理所有与LLM交互的提示词模板，便于统一维护和更新。
"""
# 集中管理所有提示词模板
PROMPT_TEMPLATES = {
    # 系统消息
    "DEFAULT_SYSTEM_MESSAGE": "You are a helpful assistant.",
    "JSON_SYSTEM_MESSAGE": "You must respond with a valid JSON object that conforms to the provided schema.",
    
    # 搜索查询生成提示词
    "SEARCH_QUERIES_TEMPLATE": """
    作为智能研究助手，你的任务是根据用户原始查询生成最多{num}个不同的、精确的搜索查询，这些查询将有助于收集有关该主题的全面信息。

    当前时间：{current_time}

    原始查询: {query}

    请以JSON数组格式返回查询语句(不要包含其他文本)，例如:
    ["查询语句1", "查询语句2", "查询语句3"]

    注意：
    1. 保留用户原始查询，并放在第一个位置，也算入总数里
    2. 与原始查询相关，但角度或焦点不同，不重复
    3. 查询语句不能偏离用户核心需求，具备实际的讨论与跟进意义，避免华而不实
    4. 查询语句具体而明确，适合搜索引擎使用
    5. 查询语句不超过10个词
    """,
    
    # 深度分析提示词
    "DEEP_ANALYSIS_TEMPLATE": """  
    针对用户问题，结合查到的数据，进行深度总结。 
    
    当前时间：{current_time}

    用户问题：{query}

    查到的数据：{summaries}
    
    你的深度总结：
    """,
    
    # 信息充分性评估提示词
    "INFORMATION_SUFFICIENCY_TEMPLATE": """
    作为智能研究助手，你的任务是评估我们目前收集的信息是否足够回答用户的查询。

    当前时间：{current_time}

    用户查询：{query}

    已收集的信息:
    {context_text}

    根据以上收集到的信息，判断是否已足够全面地回答用户查询。
    如果信息已足够，请输出"SUFFICIENT"。
    如果信息不足，请输出"INSUFFICIENT"，并简述还缺少哪些方面的信息。

    你的评估:
    """,
    
    # 额外查询生成提示词
    "ADDITIONAL_QUERIES_TEMPLATE": """
    作为智能研究助手，你的任务是基于用户的原始查询和已收集的信息，生成{num}个新的搜索查询，以补充我们还缺少的信息。

    当前时间：{current_time}

    原始查询: {original_query}

    已收集的信息:
    {context_text}

    分析上述信息后，我们还缺少哪些方面的信息？请生成{num}个新的搜索查询，以帮助我们获取更全面的信息。
    这些查询应该：
    1. 查询语句与原始查询相关，但角度或焦点不同
    2. 查询语句具体而明确，适合搜索引擎使用
    3. 查询语句能够填补已收集信息的空白
    4. 查询语句不超过10个词

    请直接列出查询，每行一个，不要有编号或其他说明。
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
    """
}

from datetime import datetime

class PromptTemplates:
    """提示词模板类，集中管理所有提示词"""
    @classmethod
    def get_system_message(cls, for_json: bool = False) -> str:
        """获取系统消息
        
        Args:
            for_json: 是否用于JSON输出
        Returns:
            str: 系统消息
        """
        if for_json:
            return PROMPT_TEMPLATES["JSON_SYSTEM_MESSAGE"]
        return PROMPT_TEMPLATES["DEFAULT_SYSTEM_MESSAGE"]
    
    @classmethod
    def format_search_queries_prompt(cls, query: str, num: int=6) -> str:
        """格式化搜索查询提示词
        
        Args:
            query: 用户查询
            num: 生成的查询数量
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["SEARCH_QUERIES_TEMPLATE"].format(query=query, num=num, current_time=datetime.now().strftime("%Y-%m-%d"))
    
    @classmethod
    def format_deep_analysis_prompt(cls, query: str, summaries: str) -> str:
        """格式化深度分析提示词
        
        Args:
            query: 用户查询
            summaries: 摘要内容
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["DEEP_ANALYSIS_TEMPLATE"].format(query=query, summaries=summaries, current_time=datetime.now().strftime("%Y-%m-%d"))
    
    @classmethod
    def format_information_sufficiency_prompt(cls, query: str, context_text: str) -> str:
        """格式化信息充分性评估提示词
        
        Args:
            query: 用户查询
            context_text: 已收集的信息文本
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["INFORMATION_SUFFICIENCY_TEMPLATE"].format(query=query, context_text=context_text, current_time=datetime.now().strftime("%Y-%m-%d"))
    
    @classmethod
    def format_additional_queries_prompt(cls, original_query: str, context_text: str, num: int=2) -> str:
        """格式化额外查询生成提示词
        
        Args:
            original_query: 原始查询
            context_text: 已收集的信息文本
            num: 生成的查询数量
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["ADDITIONAL_QUERIES_TEMPLATE"].format(
            current_time=datetime.now().strftime("%Y-%m-%d"),
            original_query=original_query, 
            context_text=context_text, 
            num=num
        )
        
    @classmethod
    def format_intent_recognition_prompt(cls, query: str) -> str:
        """格式化意图识别提示词
        
        Args:
            query: 用户查询
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["INTENT_RECOGNITION_TEMPLATE"].format(query=query, current_time=datetime.now().strftime("%Y-%m-%d"))