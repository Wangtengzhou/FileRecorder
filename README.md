# FileRecorder - 智能文件索引助手

轻量化 Windows 文件管理工具，支持本地/网络路径扫描、快速检索和 AI 智能整理。

## ✨ 功能特点

- 📁 **多目录扫描** - 支持本地磁盘和网络共享路径
- 🔍 **快速搜索** - SQLite 全文索引，毫秒级响应
- 📂 **目录浏览** - 类似资源管理器的逐级浏览体验
- 🤖 **AI 整理** - 支持 OpenAI 兼容 API 的智能文件分类（待完善）
- 💾 **备份恢复** - 数据库一键备份和恢复

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

### 5. 配置（可选）
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
├── ai/                  # AI整理模块（开发中）
├── ui/                  # 界面模块
└── data/                # 数据目录（运行时生成，已gitignore）
```

---

## ⚙️ 配置说明

复制 `config.example.json` 为 `config.json` 并按需修改：

| 配置项 | 说明 |
|--------|------|
| `ai.api_key` | OpenAI 兼容 API 的密钥 |
| `ai.base_url` | 自定义 API 地址（如 DeepSeek） |
| `scanner.batch_size` | 扫描批次大小（默认1000） |
| `scanner.ignore_patterns` | 忽略的文件/目录模式 |

> ⚠️ `config.json` 包含敏感信息，已在 `.gitignore` 中排除

---

## 🛠️ 开发环境

- **Python**: 3.12+
- **GUI**: PySide6
- **数据库**: SQLite3
- **操作系统**: Windows

---

## 📝 许可证

MIT License

