"""提示词模板管理模块
这个模块集中管理所有与LLM交互的提示词模板，便于统一维护和更新。
"""

SCENARIO_DESC = """
- general：通用信息查询，没有明确属于特定领域
- technology：人工智能、机器学习、深度学习、大模型等科技领域
- medical：医疗健康、生物技术、药物研发等医疗领域
- finance：数字货币、区块链、投资理财、银行业务等金融领域
- education：在线教育、学术研究、职业培训、教育科技等教育领域 
- entertainment：影视音乐、游戏动漫、社交媒体、流行文化等娱乐领域
- ecommerce：跨境电商、直播带货、数字营销、供应链管理等电商领域
- legal：法律咨询、合规监管、知识产权、合同纠纷等法律领域
- environment：碳中和、气候变化、可再生能源、生态保护等环境领域
- automotive：自动驾驶、电动汽车、智能座舱、车路协同等汽车科技领域
- agriculture：智慧农业、精准种植、农业无人机、农产品溯源等农业领域
- energy：新型储能、智能电网、氢能源、核能技术等能源领域
- manufacturing：工业4.0、智能工厂、3D打印、机器人自动化等制造领域
- logistics：无人配送、智能仓储、路径优化、供应链金融等物流领域
- aerospace：商业航天、卫星互联网、太空探索、航空材料等航天领域
- fashion：虚拟时装、可持续时尚、智能穿戴、服装3D打印等时尚领域
- tourism：智慧旅游、虚拟现实导览、文化遗产数字化、民宿经济等旅游领域
- sports：电子竞技、运动科技、体育大数据、智能穿戴设备等体育领域
- media：AIGC内容生成、虚拟主播、元宇宙社交、沉浸式体验等媒体领域
- security：数据隐私保护、网络安全攻防、生物识别、量子加密等安全领域
- psychology：心理健康评估、AI情感陪伴、认知行为疗法、脑机接口等心理领域
"""

# 集中管理所有提示词模板
PROMPT_TEMPLATES = {
    # 深度分析提示词
    "DEEP_ANALYSIS_TEMPLATE": """  
    针对用户问题，结合查到的数据和历史对话，进行深度总结。 
    当前时间：{current_time}
    用户问题：{query}
    查到的数据：{summaries}
    注意：不要重复总结，不要泛泛而谈，不要捏造事实。
    你的深度总结：
    """,
    
    # 信息充分性评估提示词
    "EVALUATE_INFORMATION_TEMPLATE": """
    作为智能研究助手，你的任务是评估我们目前收集的信息是否足够回答用户的查询，不够的话反思下一步如何收集信息解决用户的查询，给出包含搜索关键字的搜索URL，并且给出反思的思考过程和结论。
    当前时间：{current_time}
    用户查询：{query}
    已收集的信息:
    {article_text}
    历史对话上下文: 
    {context}
    
    以JSON格式输出：
    1 fetch_url：当有收集到的信息时，该字段为空；当用户查询中包含URL时，提取URL，一个或多个的数组结构
    2 enough字段：存放收集到的信息是否足够进行深度总结，足够值为True，不够值为False
    3 search_url：当用户查询中不包含URL时，给出与用户查询相关的更进一步的搜索URL，一个或多个的数组结构，保证搜索可用，实用主义
    4 thought：反思的思考过程和结论，使用自然语言格式，方便用户阅读
    5 query：当用户查询很明确时，直接使用用户查询；当用户查询不明确时，结合用户查询和收集到的信息给出用户想要的查询
    6 scenario：结合用户查询和收集到的信息给出当前研究领域，当用户查询很明确时，侧重用户查询来识别；当用户查询不明确时，可使用收集到的信息来识别，可选领域：
        {scenario}

    你的评估与反思:
    """,
    
    # 文章质量处理提示词
    "ARTICLE_QUALITY_TEMPLATE": """
    你是智能内容处理专家，帮我对爬取到的文章内容进行内容质量评估、智能压缩和主题提炼，最终结果以json格式输出，具体规则如下：
    1 先判断内容是否优质，将结果添加到high_quality字段(与用户查询相关且内容高质量为True、与用户查询不相关或内容低质量为False)，不优质直接结束
    2 如果内容优质，判断字数是否超过{word_count}字需要压缩，将结果添加到compress字段(需压缩值为True、不需压缩值为False)
    3 如果优质文章需要压缩，把文章压缩结果放到compressed_article字段，压缩需保留原文不要加入自己的总结，尽可能打满{word_count}字避免语义严重缺失
    4 如果内容优质，提取文章主题放在title字段，内容不超过20字
    5 如果内容优质，识别文章内容所属领域添加到scenario字段，可选领域：
        {scenario}
    6 不要输出json格式以外的文本

    当前时间：{current_time}
    用户查询：{query}
    以下是文章内容：
    {article}
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
    """
}

from datetime import datetime

class PromptTemplates:
    """提示词模板类，集中管理所有提示词"""
    @classmethod
    def format_deep_analysis_prompt(cls, query: str, summaries: str) -> str:
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
            current_time=datetime.now().strftime("%Y-%m-%d")
        )
    
    @classmethod
    def format_evaluate_information_prompt(cls, query: str, context: str, article_text: str) -> str:
        """格式化信息充分性评估提示词
        
        Args:
            query: 用户查询
            context: 历史对话上下文
            article_text: 已收集的文章文本
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["EVALUATE_INFORMATION_TEMPLATE"].format(
            query=query, 
            context=context, 
            article_text=article_text, 
            current_time=datetime.now().strftime("%Y-%m-%d"),
            scenario=SCENARIO_DESC
        )

    @classmethod
    def format_article_quality_prompt(cls, article: str, word_count: int = 5000, query: str = None) -> str:
        """格式化文章质量评估提示词
        
        Args:
            article: 文章内容
            word_count: 文章字数
        Returns:
            str: 格式化后的提示词
        """
        return PROMPT_TEMPLATES["ARTICLE_QUALITY_TEMPLATE"].format(
            article=article, 
            query=query,
            word_count=word_count,
            current_time=datetime.now().strftime("%Y-%m-%d"),
            scenario=SCENARIO_DESC
        )
    
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
            token_limit=int(token_limit * 0.8),
            current_time=datetime.now().strftime("%Y-%m-%d")
        )