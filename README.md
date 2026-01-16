# FileRecorder - 智能文件索引助手

轻量化 Windows 文件管理工具，支持本地/网络路径扫描、快速检索和 AI 智能整理。可应用于文件检索、存储目录备份、文件分类整理等场景。

## ✨ 功能特点

- 📁 **多目录扫描** - 支持本地磁盘和网络共享路径，可同时添加多个路径
- 🔍 **快速搜索** - SQLite 全文索引，毫秒级响应，支持关键词搜索
- 📂 **目录浏览** - 类似资源管理器的逐级浏览体验，支持侧边栏目录树
- 🍞 **面包屑导航** - 快速切换路径，支持前进、后退及历史记录
- 📡 **目录监控** - 自动检测文件变化，支持本地实时监控和网络轮询
- 🤖 **AI 整理** - 支持 OpenAI 兼容 API 的智能文件分类与报告生成
- 💾 **备份恢复** - 数据库一键备份和恢复

---

## 🤖 AI 整理功能

AI 整理是本工具的核心功能，可以自动识别媒体文件并生成整理报告。

### 主要特性

| 功能 | 说明 |
|------|------|
| **智能识别** | 从文件名提取标题、年份、分辨率、来源等元数据 |
| **自定义标签** | 支持任意自定义分类标签（如 电影、电视剧、动漫） |
| **二次检测** | 无法识别的文件自动结合文件夹上下文路径名称再次检测 |
| **编码提取** | 自动识别标准编码格式（ABC-123、FC2-PPV 等） |
| **原盘识别** | 支持蓝光/DVD 原盘目录结构识别 |
| **报告生成** | 生成 Markdown/HTML 格式的整理报告 |

### 使用流程

1. 点击工具栏 **🤖 AI整理** 按钮
2. 添加需要整理的目录
3. 配置扫描选项（跳过小文件、识别原盘等）
4. 管理分类标签（可添加/删除/恢复默认）
5. 可选填写提示词（如"这些是动漫"）
6. 点击 **开始整理**

### AI 配置参数

在 `config.json` 的 `ai` 部分配置（**也可在软件内设置**）：

```json
{
    "ai": {
        "api_key": "your-api-key",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "timeout": 60,
        "temperature": 0.1,
        "tpm_limit": 60000,
        "rpm_limit": 60,
        "batch_delay_ms": 500,
        "media_types": ["电影", "电视剧", "动漫", "纪录片", "综艺", "NSFW", "其他"],
        "system_preset": ""
    }
}
```

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `temperature` | 生成随机性（0-2），越低越稳定 | 0.1 |
| `tpm_limit` | 每分钟 Token 限制 | 60000 |
| `rpm_limit` | 每分钟请求限制 | 60 |
| `batch_delay_ms` | 批次间延迟（毫秒） | 500 |
| `media_types` | 自定义分类标签列表 | - |
| `system_preset` | 系统预设提示词（固定矫正规则） | "" |

### 注意事项

> ⚠️ **API 费用**：AI 整理会消耗 API Token，建议使用低成本模型如 `gpt-4o-mini`

> ⚠️ **API 速度及模型选择**：AI 整理单个批次的数量不宜太高，否则容易超时，超时时间可以在`设置`中设置。请勿使用思考类模型，太耗时。

> ⚠️ **内容审查**：某些敏感内容可能触发 AI 服务商的内容审查，导致部分文件无法识别。如果触发审查，进度框会有相应的报错提示。

> ⚠️ **二次检测**： AI 整理无法通过文件名称识别的文件会自动加入二次检测目录，结合文件夹上下文路径再次检测。

> ⚠️ **自定义标签**：如需自定义标签（如"动漫"改为"日漫"），在 AI 整理弹窗中管理，或直接修改 `config.json` 的 `media_types` 数组。

> ⚠️ **系统预设**：如果需要额外的固定矫正规则，请在`设置`中填写或在`config.json`中填写 `system_preset` 字段，无需每次运行时输入。注意**系统本身有提示词**

---

## 📡 目录监控功能

目录监控功能可自动检测已索引目录的文件变化，并实时更新索引。

### 主要特性

| 功能 | 说明 |
|------|------|
| **启动检测** | 启动时对比目录 mtime，检测文件级变化（新增/删除/修改） |
| **本地实时监控** | 基于 watchdog 库，文件变化即时响应 |
| **网络轮询监控** | 支持自定义轮询间隔（1-60分钟），带断线重试 |
| **静默更新** | 可选后台更新模式，不弹出扫描进度窗口 |
| **父子目录检测** | 自动检测父子目录冲突，提供合并选项 |
| **删除保护** | 删除已监控目录索引时弹出确认选项 |

### 使用流程

1. 点击工具栏 **📡 目录监控** 按钮
2. 添加需要监控的目录（自动识别本地/网络路径）
3. 配置轮询间隔（网络目录适用）
4. 可选开启静默更新
5. 保存配置
6. 错误信息请到`错误`->`监控错误`中查看

### 状态栏指示

- 🟢 正常 - 所有目录监控正常
- 🟡 警告 - 部分目录重试中
- 🔴 错误 - 监控出错
- ⚪ 禁用 - 监控功能未启用

---

## 🚀 快速开始

### 1. 克隆仓库
```bash
git clone https://github.com/你的用户名/FileRecorder.git
cd FileRecorder
```

### 2. 创建虚拟环境
```bash
python -m venv venv
```

### 3. 激活虚拟环境
```bash
# PowerShell
.\venv\Scripts\Activate.ps1

# CMD
.\venv\Scripts\activate.bat
```

### 4. 安装依赖
```bash
pip install -r requirements.txt
```

### 5. 配置
```bash
# 复制配置模板
copy config.example.json config.json
# 然后编辑 config.json 填入你的 AI API 密钥等信息
```

### 6. 运行程序
```bash
python main.py
```

---

## 📁 项目结构

```
FileRecorder/
├── main.py              # 程序入口
├── config.py            # 配置管理
├── config.example.json  # 配置模板
├── requirements.txt     # 依赖清单
├── database/            # 数据库模块
├── scanner/             # 文件扫描模块
├── watcher/             # 目录监控模块
│   ├── config.py        # 监控配置
│   ├── local_watcher.py # 本地实时监控
│   ├── network_poller.py# 网络轮询监控
│   └── manager.py       # 监控管理器
├── ai/                  # AI整理模块
│   ├── classifier.py    # 分类器
│   ├── prompts.py       # Prompt 模板
│   ├── parser.py        # 文件名解析
│   └── report.py        # 报告生成
├── ui/                  # 界面模块
└── data/                # 数据目录（运行时生成）
```

---

## ⚙️ 配置说明

对于使用克隆仓库的用户，需要复制 `config.example.json` 为 `config.json` 并按需修改；打包好的EXE程序在首次使用时会自动创建，无需复制：

| 配置项 | 说明 |
|--------|------|
| `ai.api_key` | OpenAI 兼容 API 的密钥 |
| `ai.base_url` | 自定义 API 地址（见下表） |
| `ai.model` | 模型名称 |
| `ai.temperature` | 生成随机性（0.1-2.0） |
| `ai.system_preset` | 系统预设提示词 |
| `scanner.batch_size` | 扫描批次大小（默认1000） |
| `scanner.ignore_patterns` | 忽略的文件/目录模式 |

> ⚠️ `config.json` 包含敏感信息，已在 `.gitignore` 中排除

### 支持的 AI 服务

本软件使用 OpenAI Chat Completions API 格式，兼容包括但不限于以下服务：

| 服务 | 接口地址 | 模型示例 |
|------|----------|----------|
| OpenAI | 留空 | gpt-4o-mini |
| DeepSeek | `https://api.deepseek.com` | deepseek-v3.1 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo |
| Ollama（本地） | `http://localhost:11434/v1` | llama3, qwen2 |
| LM Studio（本地） | `http://localhost:1234/v1` | 本地模型名 |
| Groq | `https://api.groq.com/openai/v1` | llama-3.1-70b |
| OpenRouter | `https://openrouter.ai/api/v1` | 多模型 |

---

## 🛠️ 开发环境

- **Python**: 3.12+
- **GUI**: PySide6
- **数据库**: SQLite3
- **操作系统**: Windows

---

## ⚠️ 注意事项

- **搜索结果上限**: 搜索功能最多返回 1000 条结果，这是为了保证 UI 响应速度。如果结果过多，建议细化搜索关键词或使用扩展名过滤。
- **网络路径**: 扫描网络共享路径时，确保有足够的访问权限且网络稳定。
- **AI 整理**: AI 整理功能需要配置 AI API 密钥，建议使用Grok来处理NSFW内容。接口地址需要手动加上`/v1`。

---

## 📝 许可证

GPL v3 License
