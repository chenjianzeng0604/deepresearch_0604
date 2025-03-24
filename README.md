# 深度研究助手 (Deepresearch Assistant)

一个结合规划能力、深度研究和联网搜索的智能分析系统，专注于任何领域的深度分析与内容挖掘。支持命令行和Web界面两种使用方式，可以实时获取多平台信息并生成专业分析报告。集成了定时爬取功能，可以自动追踪关键词的最新动态。

## 功能特点

- **智能规划**: 基于用户需求自动规划分析步骤和策略
- **深度研究**: 针对任何领域进行专业化分析和信息提取
- **多平台爬取**: 支持Web站点、GitHub、arXiv、微信、搜索引擎等多平台内容获取
- **定时爬虫**: 支持设置关键词和平台，按计划定时自动爬取内容并存入知识库
- **联网搜索**: 实时获取最新动态、研究成果和相关案例
- **对话式交互**: 提供自然、连贯的对话体验，支持流式输出
- **专业知识库**: 内置领域专业知识和分析框架
- **可视化分析**: 生成直观的数据可视化报告
- **多平台分发**: 支持将生成的报告分发到多个平台
- **Web界面**: 提供友好的Web交互界面，支持WebSocket实时通信

## 系统要求

- Python 3.8+
- 足够的网络带宽以支持实时搜索和内容爬取
- OpenAI API密钥（或兼容的API服务）
- Milvus向量数据库（用于知识库存储和检索）

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/deepresearch.git
cd deepresearch
```

### 2. 安装依赖

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
- apscheduler: 任务调度框架（用于定时爬虫）

### 3. 安装Milvus向量数据库

本项目使用Milvus作为向量数据库，用于存储和检索文本嵌入。您可以通过Docker快速安装：

```bash
# 安装Docker（如果尚未安装）
# Windows: 下载并安装Docker Desktop
# Linux: sudo apt-get install docker.io docker-compose

# 拉取并启动Milvus（单机版）
docker run -d --name milvus_standalone -p 19530:19530 -p 9091:9091 milvusdb/milvus:v2.3.3 standalone
```

更多安装选项请参考[Milvus官方文档](https://milvus.io/docs/install_standalone-docker.md)。

### 4. 初始化Playwright

本项目使用Playwright进行复杂网页爬取和Cloudflare绕过。首次使用需要安装浏览器：

```bash
# 安装Playwright浏览器
python -m playwright install

# 如果遇到网络问题，可以使用镜像（中国大陆用户）
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
python -m playwright install
```

### 5. 配置环境变量

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

# Milvus向量数据库配置
MILVUS_HOST=127.0.0.1       # Milvus服务器地址
MILVUS_PORT=19530           # Milvus服务器端口
COLLECTION_NAME=deepresearch # Milvus集合名称

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
- 必须确保Milvus数据库已正确配置并可访问
- 如果使用Google或Bing搜索，需要配置相应的`SEARCH_API_KEY`
- 如需使用微信公众号分发功能，请配置微信相关参数并将`WECHAT_OA_ENABLED`设为`true`
- 如需使用IP代理功能，请配置快代理相关参数

### 6. 创建必要目录

确保以下目录存在（程序会自动创建，但为了确保无误，可手动创建）：

```bash
mkdir -p data/logs
mkdir -p data/reports/images
mkdir -p data/knowledge_base
```

## 使用指南

### 命令行界面

项目提供了命令行界面，可以通过以下方式使用：

```bash
# 生成一份关于特定话题的深度分析报告
python -m src.main_cli generate --topic "人工智能在医疗领域的应用"

# 查看已生成的报告列表
python -m src.main_cli list

# 按报告类型过滤列表
python -m src.main_cli list --type "technical" --limit 20

# 分发报告到配置的平台
python -m src.main_cli distribute --id <报告ID> --platforms wechat

# 启动定时爬虫任务（每天凌晨2点和下午2点自动执行）
python -m src.main_cli scheduler-start --keywords "人工智能" "大模型" "AIGC" --platforms web_site github arxiv weixin search

# 启动定时爬虫任务并立即执行一次
python -m src.main_cli scheduler-start --keywords "人工智能" "大模型" --run-now

# 停止定时爬虫任务
python -m src.main_cli scheduler-stop
```

### Web界面

项目提供了基于FastAPI的Web界面，可以通过以下方式启动：

```bash
python -m src.main_web
```

启动后，访问 http://127.0.0.1:8000/ 即可使用Web界面。Web界面支持：

- 实时对话交互（支持流式输出）
- WebSocket通信，提供更流畅的用户体验
- 多平台内容获取（Web站点、GitHub、arXiv、微信、搜索引擎等）
- 会话管理（自动生成会话ID）
- 报告生成与管理
- 文件上传与处理

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
            "weixin",        # 微信公众号
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

### 定时爬虫功能

定时爬虫功能允许您设置关键词和平台，系统会在每天凌晨2点和下午2点自动执行爬取任务，并将内容存入知识库。

```bash
# 启动定时爬虫（默认平台包括网站、GitHub、arXiv、微信和搜索引擎）
python -m src.main_cli scheduler-start --keywords "人工智能" "大模型" "AIGC"

# 指定特定平台
python -m src.main_cli scheduler-start --keywords "人工智能" "大模型" --platforms github arxiv

# 立即执行一次爬取并继续定时执行
python -m src.main_cli scheduler-start --keywords "人工智能" "大模型" --run-now

# 停止定时爬虫
python -m src.main_cli scheduler-stop
```

定时爬虫启动后会在后台运行，可以使用Ctrl+C或scheduler-stop命令停止。定时任务会在凌晨2点和下午2点各执行一次，无需手动干预。

### 作为Python库使用

您也可以将项目作为Python库导入到自己的代码中：

```python
import asyncio
from src.agents.deepresearch_agent import DeepresearchAgent
from src.models.config import AppConfig
from src.models.response import ChatMessage

# 创建配置
config = AppConfig.from_env()  # 从环境变量加载配置
# 或者手动指定配置
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
agent = DeepresearchAgent(session_id="test_session")

# 处理一个查询
async def run_query():
    message = ChatMessage(
        session_id="test_session",
        message="分析人工智能在医疗领域的最新进展",
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

### 使用定时爬虫API

您也可以在自己的代码中使用定时爬虫功能：

```python
import asyncio
from src.scheduled_crawler import start_scheduler, stop_scheduler

async def main():
    # 启动定时爬虫
    keywords = ["人工智能", "大模型", "AIGC"]
    platforms = ["web_site", "github", "arxiv", "weixin", "search"]
    run_now = True  # 是否立即执行一次
    
    scheduler = await start_scheduler(keywords, platforms, run_now)
    
    # 保持程序运行一段时间
    try:
        print("定时任务已启动，按Ctrl+C停止")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await stop_scheduler()
        print("已停止定时任务")

if __name__ == "__main__":
    asyncio.run(main())
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
│   │   └── deepresearch_agent.py  # 深度研究智能体
│   ├── core/              # 核心处理逻辑
│   ├── crawler/           # 网页爬虫模块
│   ├── distribution/      # 内容分发模块
│   ├── models/            # 数据模型
│   ├── search/            # 联网搜索模块
│   ├── utils/             # 工具函数
│   ├── vectordb/          # 向量数据库接口
│   ├── scheduled_crawler.py # 定时爬虫模块
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

#### 1. 添加新的爬虫

在`src/crawler`目录下创建新的爬虫类，继承基础爬虫类并实现必要的方法：

```python
from src.crawler.base_crawler import BaseCrawler

class CustomCrawler(BaseCrawler):
    async def parse_sub_url(self, query: str) -> list:
        # 实现链接解析逻辑
        pass
        
    async def fetch_article_and_save2milvus(self, query: str, links: list):
        # 实现内容获取和存储逻辑
        pass
```

然后，在`src/crawler/crawler_manager.py`中注册新的爬虫：

```python
self.custom_crawler = CustomCrawler(self.config)
```

#### 2. 自定义定时任务

您可以修改`src/scheduled_crawler.py`文件来自定义定时任务的执行时间和行为：

```python
# 修改执行时间（例如每小时执行一次）
self.scheduler.add_job(
    self.scheduled_crawl,
    CronTrigger(hour='*/1'),  # 每小时执行一次
    args=[keywords, platforms],
    id='crawl_task_hourly',
    replace_existing=True
)
```

#### 3. 自定义报告生成

修改`src/core/news_processor.py`文件来自定义报告生成逻辑：

```python
async def process_tech_news(self, topic: str, include_platforms: list = None):
    # 自定义报告生成逻辑
    pass
```

#### 4. 添加新的分发平台

在`src/distribution`目录下创建新的分发平台类，并在`src/distribution/factory.py`中注册：

```python
# 创建新的分发平台类
class CustomPlatformDistributor(BaseDistributor):
    async def distribute(self, report: dict) -> dict:
        # 实现分发逻辑
        pass
        
# 在factory.py中注册
distributors["custom_platform"] = CustomPlatformDistributor(config)
```

## 问题排查

### 常见问题及解决方案

1. **API密钥错误**
   - 错误信息: "API key not valid"
   - 解决方案: 检查`.env`文件中的`OPENAI_API_KEY`是否正确设置

2. **Milvus连接失败**
   - 错误信息: "Failed to connect to Milvus"
   - 解决方案: 
     - 确认Milvus容器是否运行 `docker ps | grep milvus`
     - 检查Milvus连接参数是否正确

3. **爬虫错误**
   - 错误信息: "Failed to parse URL" 或 "Timeout"
   - 解决方案:
     - 增加超时时间 `CRAWLER_FETCH_URL_TIMEOUT=120`
     - 配置代理服务
     - 对于频繁访问被限制的网站，添加延迟

4. **定时任务未执行**
   - 检查日志文件 `data/logs/app.log`
   - 确保程序保持运行状态

### 日志和调试

开启详细日志以便调试：

```
# 在.env文件中设置
LOG_LEVEL=DEBUG
```

日志文件位于 `data/logs/app.log`

## 贡献指南

欢迎贡献代码、报告问题或提出改进建议。请遵循以下步骤：

1. Fork仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 许可证

[MIT License](LICENSE)

## 联系方式

如有任何问题，请通过以下方式联系：

- 项目维护者: 372285925@qq.com
- 项目主页: https://github.com/chenjianzeng0604/deepresearch_0604
