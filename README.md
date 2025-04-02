# 深度研究助手 (Deepresearch Assistant)

一个结合规划能力、深度研究和联网搜索的智能分析系统，专注于任何领域的深度分析与内容挖掘。支持命令行和Web界面两种使用方式，可以实时获取多平台信息并生成专业分析报告。集成了定时爬取功能，可以自动追踪关键词的最新动态，并通过邮件发送结果。

## 目录

- [功能特点](#功能特点)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
  - [命令行界面](#命令行界面)
  - [Web界面](#web界面)
  - [多平台爬虫](#多平台爬虫)
  - [定时爬虫功能](#定时爬虫功能)
  - [作为Python库使用](#作为python库使用)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [问题排查](#问题排查)
- [贡献指南](#贡献指南)
- [许可证](#许可证)
- [联系方式](#联系方式)

## 功能特点

- **智能规划**: 基于用户需求自动规划分析步骤和策略
- **深度研究**: 针对任何领域进行专业化分析和信息提取
- **多平台爬取**: 支持Web站点、GitHub、arXiv、搜索引擎等多平台内容获取
- **定时爬虫**: 支持设置关键词和平台，按计划定时自动爬取内容并存入知识库
- **联网搜索**: 实时获取最新动态、研究成果和相关案例
- **对话式交互**: 提供自然、连贯的对话体验，支持流式输出
- **专业知识库**: 内置领域专业知识和分析框架
- **可视化分析**: 生成直观的数据可视化报告
- **邮件分发**: 支持将生成的报告通过邮件发送给用户
- **Web界面**: 提供友好的Web交互界面，支持WebSocket实时通信

## 系统架构

深度研究助手采用模块化设计，主要包含以下核心组件：

- **智能体模块**: 基于大语言模型的智能代理，负责规划和执行研究任务
- **爬虫模块**: 多平台内容获取系统，支持常规网站、GitHub、arXiv等
- **向量数据库**: 使用Milvus存储和检索文本嵌入，实现高效的语义搜索
- **搜索模块**: 集成多种搜索引擎，获取实时信息
- **邮件模块**: 支持将生成的报告通过邮件发送给用户
- **Web服务**: 基于FastAPI的Web界面，提供用户友好的交互体验
- **定时任务**: 基于APScheduler的定时爬虫系统，自动追踪关键词动态

## 环境要求

- Python 3.8+
- 足够的网络带宽以支持实时搜索和内容爬取
- OpenAI API密钥（或兼容的API服务，如阿里云通义千问）
- Milvus向量数据库（用于知识库存储和检索）
- SMTP电子邮件发送服务（用于发送报告）

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/chenjianzeng0604/deepresearch_0604.git
cd deepresearch_0604
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 环境配置

复制`.env_example`文件为`.env`并根据自己的环境进行配置：

```bash
cp .env_example .env
# 使用编辑器打开.env文件进行配置
```

主要配置项包括：

```
# LLM API配置
OPENAI_API_KEY=your_api_key_here
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1  # 阿里云通义千问
# OPENAI_API_BASE=https://api.openai.com/v1  # OpenAI官方API

# LLM模型配置
LLM_MODEL=deepseek-r1                # 使用的模型名称
LLM_TEMPERATURE=0.7                  # 模型温度参数

# 邮件配置
EMAIL_ENABLED=true                   # 启用邮件发送
EMAIL_SMTP_SERVER=smtp.example.com   # SMTP服务器地址
EMAIL_SMTP_PORT=587                  # SMTP端口
EMAIL_SMTP_USERNAME=your_email@example.com  # SMTP用户名
EMAIL_SMTP_PASSWORD=your_password    # SMTP密码
EMAIL_SENDER=your_email@example.com  # 发件人
EMAIL_RECIPIENT=recipient@example.com # 收件人
EMAIL_USE_TLS=true                   # 是否使用TLS
```

### 4. 安装Milvus向量数据库

本项目使用Milvus作为向量数据库，用于存储和检索文本嵌入。您可以通过Docker快速安装：

```bash
# 安装Docker（如果尚未安装）
# Windows: 下载并安装Docker Desktop
# Linux: sudo apt-get install docker.io docker-compose

# 拉取并启动Milvus（单机版）
docker run -d --name milvus_standalone -p 19530:19530 -p 9091:9091 milvusdb/milvus:v2.3.3 standalone
```

### 5. 初始化浏览器自动化工具

部分复杂网站的爬取需要使用Playwright进行浏览器模拟：

```bash
python -m playwright install
```

### 6. 启动应用

启动Web服务：

```bash
python -m uvicorn src.app.main_web:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000 即可使用Web界面。

## 项目结构

```
├── logs/                  # 日志文件
├── src/                   # 源代码
│   ├── admin/             # 管理模块
│   │   ├── admin_web.py   # 管理员Web界面
│   │   ├── crawler_cli.py # 爬虫命令行工具
│   │   └── crawler_config_manager.py # 爬虫配置管理
│   ├── agents/            # 智能体模块
│   │   └── deepresearch_agent.py  # 深度研究智能体
│   ├── app/               # 应用模块
│   │   ├── chat_bean.py   # 聊天消息模型
│   │   └── main_web.py    # Web界面主程序
│   ├── config/            # 配置模块
│   │   └── app_config.py  # 应用配置
│   ├── database/          # 数据库模块
│   │   ├── mysql/         # MySQL数据库
│   │   ├── redis/         # Redis缓存
│   │   └── vectordb/      # 向量数据库
│   ├── log/               # 日志模块
│   ├── memory/            # 内存管理
│   ├── model/             # 模型模块
│   │   ├── embeddings/    # 嵌入模型
│   │   └── llm_client.py  # LLM客户端
│   ├── prompts/           # 提示词模板
│   ├── session/           # 会话管理
│   ├── token/             # Token计数
│   ├── tools/             # 工具模块
│   │   ├── crawler/       # 爬虫工具
│   │   ├── distribution/  # 分发工具
│   │   └── search/        # 搜索工具
│   └── utils/             # 工具函数
├── templates/             # Web模板文件
│   ├── admin/             # 管理员界面模板
│   └── app/               # 应用界面模板
├── .env                   # 环境变量配置
├── .env_example           # 环境变量配置示例
└── requirements.txt       # 项目依赖
```

## 开发指南

### 自定义扩展

您可以通过扩展以下组件来自定义系统的行为：

#### 1. 添加新的爬虫

在`src/tools/crawler`目录下创建新的爬虫类，继承基础爬虫类并实现必要的方法：

```python
from src.tools.crawler.web_crawlers import BaseCrawler

class CustomCrawler(BaseCrawler):
    async def parse_sub_url(self, query: str) -> list:
        # 实现链接解析逻辑
        pass
        
    async def fetch_article_and_save2milvus(self, query: str, links: list):
        # 实现内容获取和存储逻辑
        pass
```

然后，在爬虫管理器中注册新的爬虫。

#### 2. 自定义定时任务

您可以修改`src/tools/crawler/scheduled_crawler.py`文件来自定义定时任务的执行时间和行为：

```python
# 修改执行时间（例如每小时执行一次）
from apscheduler.triggers.cron import CronTrigger

scheduler.add_job(
    scheduled_crawl,
    CronTrigger(hour='*/1'),  # 每小时执行一次
    args=[keywords, platforms],
    id='crawl_task_hourly',
    replace_existing=True
)
```

#### 3. 自定义邮件发送

您可以通过修改`src/tools/distribution/email_sender.py`文件来自定义邮件的格式和发送逻辑：

```python
# 自定义邮件格式
async def send_email(self, subject, body, is_html=True):
    # 自定义邮件内容
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = self.sender
    msg['To'] = self.recipient
    
    # 添加自定义内容
    if is_html:
        msg.attach(MIMEText(body, 'html'))
    else:
        msg.attach(MIMEText(body, 'plain'))
    
    # 发送邮件
    # ...
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
     - 确保防火墙未阻止连接

3. **爬虫错误**
   - 错误信息: "Failed to parse URL" 或 "Timeout"
   - 解决方案:
     - 增加超时时间 `CRAWLER_FETCH_URL_TIMEOUT=120`
     - 配置代理服务
     - 对于频繁访问被限制的网站，添加延迟
     - 检查Cloudflare绕过配置

4. **邮件发送失败**
   - 错误信息: "Failed to send email" 或 "Authentication error"
   - 解决方案:
     - 确认SMTP配置是否正确
     - 检查邮件提供商是否允许应用程序访问
     - 针对Gmail等服务，可能需要开启应用专用密码

### 日志和调试

开启详细日志以便调试：

```
# 在.env文件中设置
LOG_LEVEL=DEBUG
```

日志文件位于 `logs/app.log`

## 贡献指南

欢迎贡献代码、报告问题或提出改进建议。请遵循以下步骤：

1. Fork仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 许可证

此项目采用MIT许可证 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

项目维护者: chenjianzeng - chenjianzeng@example.com

项目链接: [https://github.com/chenjianzeng0604/deepresearch_0604](https://github.com/chenjianzeng0604/deepresearch_0604)
