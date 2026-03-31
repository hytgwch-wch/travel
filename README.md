# 差旅发票自动整理系统

自动化处理邮箱中的出差发票，通过 OCR 识别发票信息并规范化命名，按行程归类，自动填写报销单。

## 功能特点

### 核心功能

- **邮箱自动同步**：通过 IMAP 自动下载新发票附件
- **智能 OCR 识别**：使用 PaddleOCR 免费识别发票内容
- **多种发票类型**：支持机票、火车、打车、接送机、住宿、餐饮等
- **标准化命名**：按日期、类型、金额、出差人自动重命名
- **行程自动归类**：基于地理位置和日期的智能行程分组
- **报销单自动生成**：基于模板自动填写差旅费报销单
- **发票去重**：自动识别并去除重复发票（行程单与发票只计一次）

### 支持的发票类型

| 类型 | 关键词 | 示例文件名 |
|------|--------|-----------|
| ✈️ 机票 | 航空、航班、行程单 | `2026-03-15_机票_杭州_北京_887.00_王春晖.pdf` |
| 🚄 火车 | 12306、车次、铁路 | `2026-03-15_火车_杭州东_上海虹桥_73.00_王春晖.pdf` |
| 🚖 打车 | 滴滴、出租车、网约车 | `2026-01-28至2026-01-28_打车_17.40_王春晖_发票.pdf` |
| 🚐 接送机 | 送机、接机、用车行程单 | `2026-03-01至2026-03-01_接送机_首都国际机场_T3_北京华融大厦_133.00_王春晖_行程单.pdf` |
| 🏨 住宿 | 酒店、宾馆、住宿费 | `2026-02-24_2026-02-25_住宿_452.00_王春晖.pdf` |
| 🍽️ 餐饮 | 餐费、餐饮、食品 | `2026-03-01_餐饮_北京_100.00_王春晖.pdf` |

## 快速开始

### 方式一：一键安装（推荐）

```bash
# 1. 克隆或下载项目
git clone https://github.com/your-repo/travel.git
cd travel

# 2. 运行安装脚本
install.bat

# 3. 编辑邮箱配置
# 编辑 config/email.yaml，填入邮箱信息

# 4. 启动程序
start.bat
```

### 方式二：手动安装

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置文件
copy config\config.yaml.example config\config.yaml
copy config\email.yaml.example config\email.yaml

# 3. 编辑配置文件
# 编辑 config/email.yaml 配置邮箱

# 4. 运行
python main.py --run
```

## 使用方法

### 命令行

```bash
# 执行一次完整的处理流程
python main.py --run

# 启动定时监控模式（每小时检查一次）
python main.py --daily

# 生成行程归类
python main.py --trips

# 模拟运行（不实际移动文件）
python main.py --dry-run

# 显示统计信息
python main.py --stats

# 生成报销单
python fill_reimbursement_template.py
```

### 批处理脚本

- `start.bat` - 启动定时监控模式
- `scripts\manual_run.bat` - 手动执行一次处理
- `scripts\setup_task.bat` - 设置 Windows 定时任务
- `scripts\remove_tasks.bat` - 删除定时任务

## 工作流程

```
邮箱 (IMAP)
    ↓
下载发票附件
    ↓
解压 ZIP 文件（支持嵌套）
    ↓
OCR 识别内容
    ↓
解析发票信息
    ↓
标准化文件命名
    ↓
按类型组织存储
    ↓
行程智能归类
    ↓
生成报销单
```

## 目录结构

```
travel/
├── config/              # 配置文件
│   ├── config.yaml              # 主配置
│   ├── email.yaml               # 邮箱配置
│   ├── parsers.yaml             # 发票解析规则
│   └── travelers.yaml           # 出差人信息
├── data/                # 数据文件
│   └── records.db               # 处理记录数据库
├── docs/                # 文档
│   ├── ENV_SETUP.md             # 环境配置说明
│   ├── USAGE.md                 # 使用教程
│   ├── TROUBLESHOOTING.md       # 故障排查指南
│   └── FAQ.md                   # 常见问题
├── invoices/            # 原始发票（按类型组织）
│   └── 2026/
│       └── 03/
│           ├── 交通/
│           ├── 住宿/
│           └── 餐饮/
├── trips/               # 行程归类
│   └── 王春晖/
│       ├── 20260301_20260304_北京-烟台/
│       │   ├── 2026-03-01_机票_杭州_北京_620.00_王春晖.pdf
│       │   ├── README.md
│       │   └── 差旅费报销单.docx
│       └── 普通打车/              # 未归类的打车发票
├── logs/                # 日志文件
├── scripts/             # 工具脚本
│   ├── setup_task.bat           # 设置定时任务
│   ├── remove_tasks.bat         # 删除定时任务
│   └── manual_run.bat           # 手动执行
├── src/                 # 源代码
├── tests/               # 单元测试
├── main.py              # 主入口
├── start.bat            # 启动脚本
├── install.bat          # 安装脚本
└── requirements.txt     # 依赖列表
```

## 配置说明

### config/email.yaml - 邮箱配置

```yaml
# IMAP 设置
imap_server: imap.zju.edu.cn
imap_port: 993
use_ssl: true

# 登录信息
username: your-email@zju.edu.cn
password: your-app-password  # 使用应用专用密码

# 邮件过滤
filters:
  senders:
    - "invoice@example.com"
  subjects:
    - "发票"
  attachment_types:
    - ".pdf"
    - ".zip"
```

### config/config.yaml - 主配置

```yaml
# 输出目录
local_output_dir: "invoices"

# 处理选项
processing:
  ocr_enabled: true
  auto_rename: true
  auto_organize: true
```

### config/travelers.yaml - 出差人信息

```yaml
default_traveler: "王春晖"

travelers:
  - name: "王春晖"
    title: "副研究员"
    department: "某某实验室"
```

## 支持的邮箱

- ✅ 浙大邮箱 (imap.zju.edu.cn)
- ✅ Gmail (imap.gmail.com)
- ✅ QQ邮箱 (imap.qq.com)
- ✅ 163邮箱 (imap.163.com)
- ✅ 企业邮箱（需确认 IMAP 地址）

## 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.8 或更高版本
- **内存**: 建议 4GB 以上
- **磁盘**: 建议 500MB 以上可用空间

## 文档

- [环境配置说明](docs/ENV_SETUP.md)
- [使用教程](docs/USAGE.md)
- [故障排查指南](docs/TROUBLESHOOTING.md)
- [常见问题](docs/FAQ.md)

## 测试

运行单元测试：

```bash
pytest tests/ -v
```

测试覆盖：132 个测试用例，100% 通过

## 开发路线图

- [x] Phase 1: 项目初始化
- [x] Phase 2: 基础模块开发
- [x] Phase 3: 核心功能开发
- [x] Phase 4: 任务调度与集成
- [x] Phase 5: 测试与优化
- [ ] Phase 6: 部署与文档 **(进行中)**
- [ ] Phase 7: 增强功能（Web 控制面板、统计报表）

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

## 致谢

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - OCR 识别引擎
- [python-docx](https://github.com/python-openxml/python-docx) - Word 文档处理
