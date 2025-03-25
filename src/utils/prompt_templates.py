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
    请根据以下用户问题，深入分析并生成相关的查询语句，查询语句要求：
    1. 保留原用户问题，并放在第一个位置，也算入总数里
    2. 根据原问题识别关键字用作查询语句，便于搜索与爬虫获取深度分析数据
    3. 关键字查询语句不能偏离用户核心需求，具备实际的讨论与跟进意义，避免华而不实
    4. 问题不重复，不带时间，查询语句的字数在10个字以内
    5. 问题可以检索到AI前沿企业与相关组织发布的最新技术，方便团队进行跟进与创新
    6. 查询语句总数不超过{num}个

    用户问题: {query}

    请以JSON数组格式返回查询语句，例如:
    ["查询语句1", "查询语句2", "查询语句3"]

    仅返回JSON格式结果，不要包含其他文本
    """,
    
    # 摘要分析提示词
    "SUMMARY_ANALYSIS_TEMPLATE": """
    请基于以下关于"{query}"的原文进行压缩改写：
    1. 严格遵循原文核心语义，不得改变作者观点及论述逻辑
    2. 将篇幅控制在1000字左右，通过提炼核心论点、删减冗余事例达成精简
    3. 保留所有关键数据、专业术语和结论性表述
    4. 维持原有章节结构，确保逻辑衔接自然流畅
    5. 使用规范化书面语，避免口语化表达
    6. 重要概念首次出现时需保留英文原词（括号加中文释义）
    特别注意：改写过程中不得添加个人解读，确保信息保真度，最终呈现既精炼又完整的内容版本。

    原文内容: {contents}
    """,
    
    # 深度分析提示词
    "DEEP_ANALYSIS_TEMPLATE": """      
    你作为AI、计算机科学和商业战略专家，需对提供的多维数据集进行深度研究。以下是具体操作指南：  

    # 角色定位
    你需同时扮演以下角色：  
    1. 数据科学家：分析数据质量和统计模式  
    2. 技术架构师(算法架构师、软件工程架构师)：评估技术可行性和实施路径  
    3. 商业顾问：识别商业价值和潜在风险  

    # 输入数据  
    研究问题：  
    {query}
    待分析数据集：  
    {summaries}

    # 分析框架  
    按以下维度进行交叉验证：  
    1. 数据质量：完整性/准确性/时效性/偏差检测  
    2. 业务影响：市场机会/成本效益/竞争格局  
    3. 技术可行性：基础设施需求/算法选择/实施难度  
    4. 风险评估：合规性/数据安全/失败场景  
    5. 创新机会：技术突破点/商业模式创新  

    # 研究步骤 
    1. 初步审查：在<数据概览>标签中记录数据特征和异常值  
    2. 模式识别：使用对比分析法找出变量间的非线性关系  
    3. 假设验证：对每个分析维度提出3个关键假设并进行验证  
    4. 深度关联：在<交叉验证>标签中分析不同维度的相互影响（如技术可行性如何制约商业价值）  

    # 输出要求 
    按以下结构输出完整报告：  
    1. 用3句话概括核心结论 
    2. 分维度列出发现（每个维度不超过3项），格式：  
    - [维度名称]  
    ▸ 发现1 (数据支撑：引用具体数据字段)  
    ▸ 发现2 (相关性分析：说明与其他维度的关联)  
    3. 提供可操作的策略建议，每条建议必须包含：  
    - 实施阶段（短期/中期/长期）  
    - 资源需求  
    - 预期收益指标  
    4. 列出3个最高优先级风险，每个风险需说明：  
    - 触发条件  
    - 影响程度（1-5级）  
    - 缓解预案  

    请先进行维度间的交叉验证分析，再生成最终报告。所有结论必须有至少两个独立维度的数据支持。  
    """,
    
    # 信息充分性评估提示词
    "INFORMATION_SUFFICIENCY_TEMPLATE": """
    作为一个研究助手，你的任务是评估我们目前收集的信息是否足够回答用户的查询。

    用户查询: {query}

    已收集的信息:
    {context_text}

    根据以上收集到的信息，判断是否已足够全面地回答用户查询。
    如果信息已足够，请输出"SUFFICIENT"。
    如果信息不足，请输出"INSUFFICIENT"，并简述还缺少哪些方面的信息。

    你的评估:
    """,
    
    # 额外查询生成提示词
    "ADDITIONAL_QUERIES_TEMPLATE": """
    作为一个研究助手，你的任务是基于用户的原始查询和已收集的信息，生成{num}个新的搜索查询，以补充我们还缺少的信息。

    原始查询: {original_query}

    已收集的信息:
    {context_text}

    分析上述信息后，我们还缺少哪些方面的信息？请生成{num}个新的搜索查询，以帮助我们获取更全面的信息。
    这些查询应该：
    1. 与原始查询相关，但角度或焦点不同
    2. 具体而明确，适合搜索引擎使用
    3. 能够填补已收集信息的空白
    4. 每个查询不超过10个词

    请直接列出查询，每行一个，不要有编号或其他说明：
    """
}

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
            
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["SEARCH_QUERIES_TEMPLATE"].format(query=query, num=num)
    
    @classmethod
    def format_summary_analysis_prompt(cls, query: str, contents: str) -> str:
        """格式化摘要分析提示词
        
        Args:
            query: 用户查询
            contents: 文章内容
            
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["SUMMARY_ANALYSIS_TEMPLATE"].format(query=query, contents=contents)
    
    @classmethod
    def format_deep_analysis_prompt(cls, query: str, summaries: str) -> str:
        """格式化深度分析提示词
        
        Args:
            query: 用户查询
            summaries: 摘要内容
            
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["DEEP_ANALYSIS_TEMPLATE"].format(query=query, summaries=summaries)
    
    @classmethod
    def format_information_sufficiency_prompt(cls, query: str, context_text: str) -> str:
        """格式化信息充分性评估提示词
        
        Args:
            query: 用户查询
            context_text: 已收集的信息文本
            
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["INFORMATION_SUFFICIENCY_TEMPLATE"].format(query=query, context_text=context_text)
    
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
        return PROMPT_TEMPLATES["ADDITIONAL_QUERIES_TEMPLATE"].format(original_query=original_query, context_text=context_text, num=num)