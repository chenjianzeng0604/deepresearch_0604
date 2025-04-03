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
    
    # 推荐问题生成提示词
    "RECOMMENDED_QUESTIONS_TEMPLATE": """
    基于当前对话内容和历史记忆，生成不超过3个相关的推荐问题，这些问题应该是用户可能想要进一步提问的内容。

    当前时间：{current_time}

    用户最近的问题：{query}

    你的回答：{response}

    历史对话上下文：{context}

    请生成1-3个简洁、相关且有价值的后续问题。这些问题应该：
    1. 与当前话题高度相关
    2. 能够引导更深入的探讨
    3. 简短明了（每个问题不超过15个字）

    以JSON数组格式输出推荐问题:
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
    - general：通用知识，包括一般性问题、日常生活、基础知识等
    - technology：技术领域，包括编程语言、软件开发、人工智能、技术框架等
    - medical：医学健康，包括疾病症状、治疗方法、医学常识、健康建议等
    
    以JSON格式输出：
    1 category字段：存放最匹配的领域名称（仅限上述选项中的一个：general, technology, medical）
    2 confidence字段：置信度（0-1之间的浮点数）
    3 explanation字段：解释原因

    你的分析结果:
    """,
    
    # 文章质量评估提示词
    "ARTICLE_QUALITY_TEMPLATE": """
    作为内容质量评估专家，请评估以下文章的质量、相关性和实用性。

    当前时间：{current_time}

    文章内容（约{word_count}字）:
    {article}

    请从以下维度评估：
    1. 内容质量 (1-10分)：信息准确性，论证逻辑，叙述清晰度
    2. 专业程度 (1-10分)：专业术语使用，专业观点深度，行业理解水平
    3. 信息密度 (1-10分)：有效信息的密集程度，冗余内容比例
    4. 实用价值 (1-10分)：对读者的参考价值和实际应用价值
    5. 时效性 (1-10分)：信息的时新程度，是否过时
    
    以JSON格式输出：
    1 quality_score字段：总体质量得分（1-10分的浮点数）
    2 dimensions字段：包含各维度得分的对象
    3 reasoning字段：评分理由的简要说明
    4 keep_content字段：布尔值，表示是否值得保留

    你的评估:
    """,
    
    # 内容压缩统一管理提示词
    "CONTENT_COMPRESSION_TEMPLATE": """
    作为AI研究助手，您的任务是对已收集的多篇文章进行分析，根据与查询的相关性和信息价值，决定如何压缩和优化这些内容。
    
    当前时间：{current_time}
    
    用户查询: {query}
    
    当前已收集的文章内容:
    {existing_content}
    
    新文章内容:
    {new_content}
    
    您需要:
    1. 评估每篇文章与查询的相关性
    2. 确定哪些文章需要保留，哪些可以丢弃或压缩
    3. 对保留的文章进行适当压缩，确保总内容不超过{token_limit}个token
    4. 确保最重要和最相关的信息得到保留
    
    请以JSON格式输出结果:
    ```
    {{
      "decisions": {{
        "reasoning": "您如何做出压缩决策的解释",
        "strategy": "您采用的压缩策略"
      }},
      "compressed_results": [
        {{
          "original_index": 0,  // 对应原始文章的索引，新文章用-1表示
          "url": "文章链接",
          "title": "文章标题",
          "content": "压缩后的内容",
          "compressed": true  // 是否经过压缩
        }},
        // 更多文章...
      ]
    }}
    ```
    """,
    
    # 内容压缩系统消息
    "CONTENT_COMPRESSION_SYSTEM_MESSAGE": """你是一个专业的内容压缩和优化助手。你的任务是高效地压缩多篇文章内容，同时保持原有的核心信息和价值。请确保输出格式严格符合JSON规范，以便系统能够正确解析。""",

    # 记忆生成提示词模板
    "MEMORY_GENERATION_TEMPLATE": """
    作为智能记忆管理助手，你的任务是从以下对话历史中提取重要信息，生成结构化的长期记忆。

    当前时间：{current_time}

    对话历史：
    {chat_history}

    请提取以下内容：
    1. 用户提到的关键主题和问题
    2. 重要的事实性信息和知识点
    3. 用户表达的偏好、兴趣和目标
    4. 以前的查询和对话中已解决的问题

    生成一段简洁但全面的记忆摘要，该摘要将用于未来对话中，帮助理解用户的背景和需求。摘要应包含上下文信息，但不要过于冗长。

    你的记忆摘要:
    """,
    
    # 记忆生成系统消息
    "MEMORY_GENERATION_SYSTEM_MESSAGE": """你是一个专业的记忆管理助手。你的任务是从对话历史中提取关键信息，生成结构化的长期记忆。请确保记忆摘要简洁、信息丰富且便于未来检索。记忆应聚焦于用户的需求、偏好和历史交互中的重要事实。""",
    
    # 用户特征提取提示词模板
    "USER_FEATURE_EXTRACTION_TEMPLATE": """
    作为用户特征分析专家，你的任务是从以下对话历史中提取用户的特征信息。

    当前时间：{current_time}

    对话历史：
    {chat_history}

    请分析并提取以下用户特征：
    1. 兴趣领域：用户表现出兴趣的主题和领域
    2. 知识水平：用户在不同领域的专业程度
    3. 交互风格：用户的沟通方式和偏好
    4. 目标和需求：用户希望解决的问题和达成的目标
    5. 语言习惯：用户常用的表达方式和词汇选择

    以JSON格式输出用户特征:
    ```
    {
      "features": {
        "interests": ["兴趣1", "兴趣2", ...],
        "knowledge_level": {
          "领域1": "初级/中级/高级",
          "领域2": "初级/中级/高级",
          ...
        },
        "interaction_style": "描述用户的交互风格",
        "goals": ["目标1", "目标2", ...],
        "language_preferences": "描述用户的语言习惯"
      }
    }
    ```
    """,
    
    # 用户特征提取系统消息
    "USER_FEATURE_EXTRACTION_SYSTEM_MESSAGE": """你是一个专业的用户特征分析专家。你的任务是从对话历史中提取用户的特征信息，包括兴趣、知识水平、交互风格、目标和语言习惯。请确保输出格式严格符合JSON规范，以便系统能够正确解析。"""
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
    
    @classmethod
    def format_content_compression_prompt(cls, query: str, existing_content: str, new_content: str, token_limit: int) -> str:
        """格式化内容压缩统一管理提示词
        
        Args:
            query: 用户查询
            existing_content: 现有内容集合
            new_content: 新内容
            token_limit: token限制
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["CONTENT_COMPRESSION_TEMPLATE"].format(
            query=query,
            existing_content=existing_content,
            new_content=new_content,
            token_limit=int(token_limit * 0.8)  # 80%的token限制
        )
    
    @classmethod
    def get_content_compression_system_message(cls) -> str:
        """获取内容压缩系统消息
        
        Returns:
            str: 内容压缩系统消息
        """
        return PROMPT_TEMPLATES["CONTENT_COMPRESSION_SYSTEM_MESSAGE"]
        
    @classmethod
    def format_memory_generation_prompt(cls, chat_history):
        """格式化记忆生成提示词
        
        Args:
            chat_history: 对话历史列表
        
        Returns:
            str: 格式化后的提示词
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 将对话历史格式化为文本
        history_text = ""
        for msg in chat_history:
            role = "用户" if msg.get("role") == "user" else "助手"
            history_text += f"{role}: {msg.get('content', '')}\n\n"
        
        return PROMPT_TEMPLATES["MEMORY_GENERATION_TEMPLATE"].format(
            current_time=current_time,
            chat_history=history_text
        )
    
    @classmethod
    def get_memory_generation_system_message(cls):
        """获取记忆生成系统消息
        
        Returns:
            str: 记忆生成系统消息
        """
        return PROMPT_TEMPLATES["MEMORY_GENERATION_SYSTEM_MESSAGE"]
    
    @classmethod
    def format_user_feature_extraction_prompt(cls, chat_history):
        """格式化用户特征提取提示词
        
        Args:
            chat_history: 对话历史列表
        
        Returns:
            str: 格式化后的提示词
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 将对话历史格式化为文本
        history_text = ""
        for msg in chat_history:
            role = "用户" if msg.get("role") == "user" else "助手"
            history_text += f"{role}: {msg.get('content', '')}\n\n"
        
        return PROMPT_TEMPLATES["USER_FEATURE_EXTRACTION_TEMPLATE"].format(
            current_time=current_time,
            chat_history=history_text
        )
    
    @classmethod
    def get_user_feature_extraction_system_message(cls):
        """获取用户特征提取系统消息
        
        Returns:
            str: 用户特征提取系统消息
        """
        return PROMPT_TEMPLATES["USER_FEATURE_EXTRACTION_SYSTEM_MESSAGE"]
    
    @classmethod
    def format_recommended_questions_prompt(cls, query: str, response: str, context: str) -> str:
        """格式化推荐问题生成提示词
        
        Args:
            query: 用户最近的问题
            response: 您的回答
            context: 历史对话上下文
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["RECOMMENDED_QUESTIONS_TEMPLATE"].format(
            query=query, 
            response=response, 
            context=context,
            current_time=datetime.now().strftime("%Y-%m-%d")
        )