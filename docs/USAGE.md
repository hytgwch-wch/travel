# 使用教程

## 快速开始

### 方式一：一键启动

双击 `start.bat` 即可启动定时监控模式，系统将：
1. 每小时检查一次新邮件
2. 自动下载发票附件
3. 解析发票信息
4. 重命名并归类文件
5. 生成行程汇总

### 方式二：手动执行

双击 `scripts\manual_run.bat` 执行一次完整的处理流程。

### 方式三：命令行

```bash
# 执行一次完整的处理流程
python main.py --run

# 启动定时监控模式
python main.py --daily

# 生成行程归类
python main.py --trips

# 模拟运行（不实际移动文件）
python main.py --dry-run

# 指定配置文件
python main.py --config path/to/config.yaml

# 显示统计信息
python main.py --stats
```

## 主要功能

### 1. 邮箱同步

系统自动从邮箱下载发票附件：

- 支持的邮件类型：浙大邮箱、Gmail、QQ邮箱等（IMAP协议）
- 支持的附件格式：PDF、图片（JPG、PNG等）
- 自动解压 ZIP 压缩包（支持嵌套）
- 自动去重（不重复下载已处理的文件）

**配置**：编辑 `config/email.yaml`

```yaml
imap_server: imap.zju.edu.cn
imap_port: 993
username: your-email@zju.edu.cn
password: your-app-password  # 使用应用专用密码，非登录密码
```

### 2. 发票解析

自动识别以下类型发票：

| 类型 | 关键词 | 归类 |
|------|--------|------|
| 机票 | 航空、航班、行程单 | 交通 |
| 火车 | 12306、车次、铁路 | 交通 |
| 打车 | 滴滴、出租车、网约车 | 交通 |
| 接送机 | 送机、接机、用车行程单 | 交通 |
| 住宿 | 酒店、宾馆、住宿费 | 住宿 |
| 餐饮 | 餐费、餐饮、食品 | 餐饮 |

**解析内容**：
- 出差人姓名
- 日期
- 金额
- 出发地/目的地（交通类）
- 城市（餐饮类）

### 3. 文件重命名

自动生成标准化文件名：

```
{日期}_{类型}_{起点}_{终点}_{金额}_{出差人}.pdf
```

示例：
- `2026-03-15_机票_杭州_北京_887.00_王春晖.pdf`
- `2026-01-28至2026-01-28_打车_17.40_王春晖_发票.pdf`
- `2026-02-24_2026-02-25_住宿_452.00_王春晖.pdf`

### 4. 行程归类

自动将发票按行程归类：

```
trips/
├── 王春晖/
│   ├── 20260301_20260304_北京-烟台/
│   │   ├── 2026-03-01_机票_杭州_北京_620.00_王春晖.pdf
│   │   ├── 2026-03-01_接送机_首都国际机场_T3_北京华融大厦_133.00_王春晖.pdf
│   │   └── README.md (行程汇总)
│   ├── 20260310_20260311_上海/
│   │   └── ...
│   └── 普通打车/
│       └── (无法归类的打车发票)
```

**归类规则**：
- 基于地理位置连续性
- 支持多城市连续行程
- 自动匹配同期的打车、接送机、住宿发票
- 生成行程汇总 README.md

### 5. 报销单生成

自动填写差旅费报销单：

```bash
python fill_reimbursement_template.py
```

**功能**：
- 基于模板自动生成报销单
- 自动填写出差人信息
- 自动填写出差事由、地点、日期
- 自动计算交通费、住宿费
- 支持发票去重（行程单与发票只计一次）

## 配置文件

### config.yaml - 主配置

```yaml
# 输出目录
local_output_dir: "invoices"

# 邮箱同步
email:
  enabled: true
  filter_days: 30  # 只下载最近30天的邮件

# 发票处理
processing:
  ocr_enabled: true
  auto_rename: true
  auto_organize: true
```

### email.yaml - 邮箱配置

```yaml
# IMAP 设置
imap_server: imap.zju.edu.cn
imap_port: 993
use_ssl: true

# 登录信息
username: your-email@zju.edu.cn
password: your-app-password

# 邮件过滤
filters:
  senders:
    - "invoice@example.com"
  subjects:
    - "发票"
    - "行程单"
  attachment_types:
    - ".pdf"
    - ".zip"
```

### travelers.yaml - 出差人信息

```yaml
default_traveler: "王春晖"

travelers:
  - name: "王春晖"
    title: "副研究员"
    department: "某某实验室"

  - name: "其他出差人"
    title: "研究员"
    department: "某某部门"
```

## 工作流程

```
┌─────────────┐
│  邮箱同步   │ → 下载发票附件
└──────┬──────┘
       ↓
┌─────────────┐
│  OCR 识别   │ → 提取发票信息
└──────┬──────┘
       ↓
┌─────────────┐
│  信息解析   │ → 结构化数据
└──────┬──────┘
       ↓
┌─────────────┐
│  文件重命名 │ → 标准化文件名
└──────┬──────┘
       ↓
┌─────────────┐
│  行程归类   │ → 按行程分组
└──────┬──────┘
       ↓
┌─────────────┐
│  报销单生成 │ → 填写报销单
└─────────────┘
```

## 常见使用场景

### 场景一：首次使用

1. 运行 `install.bat` 安装依赖
2. 编辑 `config/email.yaml` 配置邮箱
3. 运行 `start.bat` 启动监控

### 场景二：补录历史发票

1. 将历史发票放入 `invoices/` 目录
2. 运行 `python main.py --run` 处理
3. 运行 `python main.py --trips` 生成行程

### 场景三：生成报销单

1. 确保 `trips/` 目录下已有行程文件夹
2. 将报销单模板放到 `trips/报销单.doc`
3. 运行 `python fill_reimbursement_template.py`

### 场景四：查看处理记录

```bash
python main.py --stats
```

## 故障排查

详见 [故障排查指南](TROUBLESHOOTING.md)
