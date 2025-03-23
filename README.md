# 深度研究助手 (Deepresearch Assistant)

一个结合规划能力、深度研究和联网搜索的智能对话系统，专注于科技新闻和学术论文的深度分析。支持命令行和Web界面两种使用方式，可以实时获取多平台信息并生成专业分析报告。

## 功能特点

- **智能规划**: 基于用户需求自动规划分析步骤和策略
- **深度研究**: 针对科技新闻和学术论文进行专业化分析和信息提取
- **多平台爬取**: 支持Web站点、GitHub、arXiv、微博、微信、Twitter等多平台内容获取
- **联网搜索**: 实时获取最新科技动态、研究成果和相关案例
- **对话式交互**: 提供自然、连贯的对话体验，支持流式输出
- **专业知识库**: 内置科技领域的专业知识和分析框架
- **可视化分析**: 生成直观的数据可视化报告
- **Web界面**: 提供友好的Web交互界面，支持WebSocket实时通信

## 系统要求

- Python 3.8+
- 足够的网络带宽以支持实时搜索和内容爬取
- OpenAI API密钥（或兼容的API服务）
- Milvus向量数据库（用于知识库存储和检索）

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括：
- langchain 和 langchain-openai: 大语言模型应用框架
- openai: OpenAI API客户端
- fastapi 和 uvicorn: Web服务框架
- beautifulsoup4 和 requests: 网页爬取和解析
- pymilvus: 向量数据库客户端
- FlagEmbedding: 文本嵌入模型
- playwright: 浏览器自动化工具（用于复杂网页爬取）

### 安装Milvus向量数据库

本项目使用Milvus作为向量数据库，用于存储和检索文本嵌入。您可以通过Docker快速安装：

```bash
# 安装Docker（如果尚未安装）
# Windows: 下载并安装Docker Desktop
# Linux: sudo apt-get install docker.io docker-compose

# 拉取并启动Milvus（单机版）
docker run -d --name milvus_standalone -p 19530:19530 -p 9091:9091 milvusdb/milvus:v2.3.3 standalone
```

更多安装选项请参考[Milvus官方文档](https://milvus.io/docs/install_standalone-docker.md)。

### 初始化Playwright

本项目使用Playwright进行复杂网页爬取和Cloudflare绕过。首次使用需要安装浏览器：

```bash
# 安装Playwright浏览器
python -m playwright install

# 如果遇到网络问题，可以使用镜像（中国大陆用户）
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
python -m playwright install
```

### 配置环境变量

1. 将项目根目录中的`.env_example`文件复制为`.env`：

```bash
# Windows
copy .env_example .env

# Linux/macOS
cp .env_example .env
```

2. 使用文本编辑器打开`.env`文件，根据需要修改配置项，**特别是需要填写您自己的API密钥**：

```
# 必需配置 - 必须填写您自己的API密钥
OPENAI_API_KEY=your_openai_api_key  # 替换为您的OpenAI API密钥

# API基础URL配置 - 根据您使用的服务提供商调整
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1  # 阿里云通义千问兼容模式
# OPENAI_API_BASE=https://api.openai.com/v1  # OpenAI官方API

# 服务器配置
HOST=127.0.0.1  # Web服务监听地址
PORT=8000       # Web服务端口
DEBUG=true      # 是否启用调试模式

# 应用信息
APP_NAME=deepresearch_0604  # 应用名称
APP_VERSION=0.1.0           # 应用版本
LOG_LEVEL=INFO              # 日志级别

# LLM模型配置
LLM_MODEL=deepseek-r1                # 使用的模型名称
LLM_TEMPERATURE=0.7                  # 模型温度参数
LLM_MAX_TOKENS=4096                  # 最大输出token数
LLM_USE_TOOL_MODEL=qwen2.5-72b-instruct  # 工具调用模型

# 搜索引擎配置
WEB_SEARCH_ENABLED=true    # 是否启用网络搜索
SEARCH_ENGINE=google       # 搜索引擎（google, bing, duckduckgo等）
SEARCH_API_KEY=your_search_api_key  # 搜索API密钥（如使用Google或Bing需要）

# 文件上传配置
MAX_UPLOAD_SIZE=104857600  # 最大上传文件大小（字节）
SUPPORTED_EXTENSIONS=.pdf,.docx,.txt,.md,.csv  # 支持的文件类型

# 微信公众号配置（可选）
WECHAT_OA_ENABLED=false    # 是否启用微信公众号分发
WECHAT_API_URL=https://api.weixin.qq.com  # 微信API URL
WECHAT_OA_APP_ID=your_wechat_app_id      # 微信公众号AppID
WECHAT_OA_APP_SECRET=your_wechat_app_secret  # 微信公众号AppSecret

# 快代理配置（用于爬虫IP代理）
KDL_PROXIES_SERVER=your_kdl_server        # 快代理服务器地址
KDL_PROXIES_USERNAME=your_kdl_username    # 快代理用户名
KDL_PROXIES_PASSWORD=your_kdl_password    # 快代理密码

# 爬虫配置
CRAWLER_MAX_LINKS_RESULT=10       # 每次爬取的最大链接数
CRAWLER_EXTRACT_PDF_TIMEOUT=30     # PDF提取超时时间（秒）
CRAWLER_FETCH_URL_TIMEOUT=60       # URL获取超时时间（秒）

# Cloudflare绕过配置
CLOUDFLARE_BYPASS_POST_SUBMIT_WAIT=30000    # 提交后等待时间（毫秒）
CLOUDFLARE_BYPASS_WAIT_FOR_TIMEOUT=10000    # 等待超时时间（毫秒）
```

**重要提示**：
- 必须配置`OPENAI_API_KEY`才能使用LLM功能
- 如果使用Google或Bing搜索，需要配置相应的`SEARCH_API_KEY`
- 如需使用微信公众号分发功能，请配置微信相关参数并将`WECHAT_OA_ENABLED`设为`true`
- 如需使用IP代理功能，请配置快代理相关参数

### 使用命令行界面

项目提供了命令行界面，可以通过以下方式使用：

```bash
# 生成一份关于特定话题的技术报告
python -m src.main_cli generate --topic "人工智能在医疗领域的应用"

# 查看已生成的报告列表
python -m src.main_cli list

# 删除特定报告
python -m src.main_cli delete --id <报告ID>

# 分发报告到配置的平台
python -m src.main_cli distribute --id <报告ID> --platforms wechat
```

### 使用Web界面

项目提供了基于FastAPI的Web界面，可以通过以下方式启动：

```bash
python -m src.main_web
```

启动后，访问 http://127.0.0.1:8000/ 即可使用Web界面。Web界面支持：

- 实时对话交互（支持流式输出）
- WebSocket通信，提供更流畅的用户体验
- 多平台内容获取（Web站点、GitHub、arXiv、微博、微信、Twitter等）
- 会话管理（自动生成会话ID）

### 各平台爬虫使用方法

在使用时，您可以指定需要爬取的平台：

```python
# 在Python代码中指定平台
message = ChatMessage(
    session_id="test_session",
    message="查询内容",
    metadata={
        "platforms": [
            "web_site",      # 普通网站
            "search",        # 搜索引擎
            "github",        # GitHub仓库
            "arxiv",         # arXiv论文
            "wechat",        # 微信公众号
            "weibo",         # 微博
            "twitter"        # Twitter/X
        ]
    }
)
```

在命令行中：

```bash
python -m src.main_cli generate --topic "人工智能在医疗领域的应用" --platforms web_site,search,github,arxiv
```

### 作为Python库使用

您也可以将项目作为Python库导入到自己的代码中：

```python
import asyncio
from src.agents.deepresearch_agent import DeepresearchAgent
from src.models.config import AppConfig
from src.models.response import ChatMessage

# 创建配置
config = AppConfig(
    llm={
        "api_key": "your_openai_api_key",
        "model": "gpt-4-turbo",
        "temperature": 0.2
    },
    search={
        "engine": "duckduckgo",
        "enabled": True
    }
)

# 创建代理实例
agent = DeepresearchAgent(session_id="test_session", config=config)

# 处理一个查询
async def run_query():
    message = ChatMessage(
        session_id="test_session",
        message="人工智能在医疗领域的最新进展是什么？",
        metadata={"platforms": ["web_site", "search", "github", "arxiv"]}
    )
    
    async for chunk in agent.process_stream(message):
        if isinstance(chunk, dict):
            print(f"元数据: {chunk}")
        else:
            print(chunk, end="", flush=True)
    
# 运行异步函数
asyncio.run(run_query())
```

## 项目结构

```
├── data/                  # 数据存储目录
│   ├── logs/              # 日志文件
│   ├── reports/           # 生成的报告
│   │   └── images/        # 报告图片
│   └── knowledge_base/    # 知识库数据
├── src/                   # 源代码
│   ├── agents/            # 智能体模块
│   ├── core/              # 核心处理逻辑
│   ├── crawler/           # 网页爬虫模块
│   ├── distribution/      # 内容分发模块
│   ├── models/            # 数据模型
│   ├── search/            # 联网搜索模块
│   ├── utils/             # 工具函数
│   ├── vectordb/          # 向量数据库接口
│   ├── main_cli.py        # 命令行界面
│   └── main_web.py        # Web界面
├── templates/             # Web模板文件
├── .env                   # 环境变量配置
├── .env_example           # 环境变量配置示例
└── requirements.txt       # 项目依赖
```

## 开发指南

### 自定义扩展

您可以通过扩展以下组件来自定义系统的行为：

- **搜索引擎**: 实现自定义的搜索提供商
- **爬虫模块**: 添加新的网站爬虫或内容提取器
- **处理器**: 自定义如何生成和格式化回复
- **规划器**: 修改规划
