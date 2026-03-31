# ROADMAP.md - 项目任务规划

## 任务状态说明
- `[TODO]`: 待开始
- `[DOING]`: 进行中
- `[DONE]`: 已完成
- `[BLOCKED]`: 被阻塞

---

## Phase 1: 项目初始化 [DONE]

### 1.1 项目结构搭建 [DONE]
- [x] 创建目录结构（src/, config/, data/, temp/, invoices/, logs/, tests/, trips/）
- [x] 初始化 requirements.txt
- [x] 创建 .gitignore 文件
- [x] 初始化 README.md

### 1.2 配置文件创建 [DONE]
- [x] 创建 config/config.yaml（主配置）
- [x] 创建 config/parsers.yaml（发票解析规则）
- [x] 创建 config/travelers.yaml（出差人信息）
- [x] 创建 config/email.yaml（邮箱配置）

### 1.3 依赖安装 [DONE]
- [x] 安装 PaddleOCR 及依赖
- [x] 安装 python-docx
- [x] 安装 pywin32（用于 .doc 文件处理）
- [x] 安装其他依赖包

---

## Phase 2: 基础模块开发 [DONE]

### 2.1 配置管理模块 (src/config.py) [DONE]
- [x] 实现配置加载类
- [x] 实现 YAML 配置解析
- [x] 配置验证逻辑
- [x] 邮箱配置支持

### 2.2 数据库模块 (src/database.py) [DONE]
- [x] 实现 RecordDatabase 类
- [x] 创建表结构（processed_files）
- [x] 实现 CRUD 操作接口
- [x] 添加数据库迁移支持
- [x] 邮件 UID 追踪功能

---

## Phase 3: 核心功能开发 [DONE]

### 3.1 邮箱同步模块 (src/email_sync.py) [DONE]
- [x] 封装 IMAP 协议调用
- [x] 实现 list_emails() 方法
- [x] 实现 _download_attachments() 方法
- [x] 实现 sync_new_files() 方法
- [x] 实现 _extract_archive() 方法（支持嵌套 ZIP）
- [x] 添加邮件过滤规则（EmailFilter 类）
- [x] 添加错误重试机制

### 3.2 OCR 引擎模块 (src/ocr_engine.py) [DONE]
- [x] 初始化 PaddleOCR
- [x] 实现 recognize() 方法（图片）
- [x] 实现 recognize_pdf() 方法
- [x] 实现 recognize_bytes() 方法
- [x] 实现 recognize_auto() 方法
- [x] 添加预处理逻辑（图片增强）

### 3.3 发票解析模块 (src/parser.py) [DONE]
- [x] 实现 InvoiceType 枚举
- [x] 实现 InvoiceInfo 数据类
- [x] 实现 detect_type() 方法（类型检测）
- [x] 实现 parse() 方法（信息提取）
- [x] 机票行程日期提取（备注中的日期）
- [x] 出差人姓名过滤（排除"工号"等占位符）
- [x] 多种文件名格式支持

### 3.4 文件重命名模块 (src/renamer.py) [DONE]
- [x] 实现 generate_name() 方法
- [x] 实现命名规则映射（7种发票类型）
- [x] 实现 make_unique() 方法（处理冲突）
- [x] 添加文件名合法化处理

### 3.5 文件组织模块 (src/organizer.py) [DONE]
- [x] 实现 get_target_path() 方法
- [x] 实现 organize() 方法
- [x] 自动创建目标目录结构
- [x] 添加 dry_run 模式支持

---

## Phase 4: 任务调度与集成 [DONE]

### 4.1 调度器模块 (src/scheduler.py) [DONE]
- [x] 实现 TaskScheduler 类
- [x] 实现 run_once() 方法（完整流程）
- [x] 邮箱/百度网盘自动切换
- [x] 添加日志记录（每步操作）
- [x] 实现错误处理与恢复
- [x] 添加进度统计（TaskResult）

### 4.2 主入口脚本 [DONE]
- [x] 创建 main.py（命令行入口）
- [x] 实现命令行参数解析
  - [x] --run: 执行一次任务
  - [x] --daily: 启动定时任务
  - [x] --trips: 生成行程归类
  - [x] --dry-run: 模拟运行
  - [x] --stats: 显示统计信息
  - [x] --config: 指定配置文件
- [x] 添加使用帮助

### 4.3 行程归类模块 (src/trip_grouper.py) [DONE]
- [x] 实现 TripGrouper 类
- [x] 实现 _build_trip_chains() 方法
- [x] 地理位置连续性检查
- [x] 支持多城市连续行程
- [x] 自动匹配打车、接送机、住宿发票
- [x] 未归类发票放入"普通打车"文件夹
- [x] 生成行程汇总 README.md

---

## Phase 5: 测试与优化 [DONE]

### 5.1 单元测试 [DONE]
- [x] parser.py 测试（20个测试用例，全部通过）
- [x] trip_grouper.py 测试（22个测试用例，全部通过）
- [x] ocr_engine.py 测试（7个测试用例，全部通过）
- [x] fill_reimbursement_template.py 测试（29个测试用例，全部通过）
- [x] renamer.py 测试（34个测试用例，全部通过）
- [x] organizer.py 测试（20个测试用例，全部通过）
- **总计：132个测试用例，全部通过（100%通过率）**

### 5.2 集成测试 [DONE]
- [x] 创建集成测试套件 (tests/integration/)
- [x] 端到端工作流测试
- [x] 数据库持久化测试
- [x] 文件冲突处理测试
- [x] 嵌套 ZIP 解压测试
- [x] 分页和统计功能测试
- [x] 重复预防测试
- **总计：11 个集成测试用例，全部通过**

### 5.3 日志与监控 [DONE]
- [x] 创建日志配置模块 (src/logging_config.py)
- [x] 配置 loguru 日志格式（彩色控制台输出）
- [x] 添加文件日志（按日期滚动）
- [x] 添加错误日志文件（单独记录）
- [x] 添加处理统计日志 (StatisticsLogger)
- [x] 添加错误告警机制 (ErrorAlertManager)
- [x] 日志压缩（30天保留，错误日志90天）

### 5.4 错误处理优化 [DONE]
- [x] 创建错误处理模块 (src/error_handlers.py)
- [x] OCR 识别失败的处理策略 (OCRFallbackHandler)
- [x] 解析失败时的降级方案 (ParseFallbackHandler)
- [x] 网络错误的重试机制 (@retry_on_error 装饰器)
- [x] 添加待处理文件列表 (ManualReviewQueue)
- [x] Web API 接口（/api/review/*）
- [x] 人工审核标记功能

---

## Phase 6: 部署与文档 [DONE]

### 6.1 部署配置 [DONE]
- [x] 创建 Windows 任务计划程序配置脚本 (scripts/setup_task.bat)
- [x] 创建启动脚本（start.bat）
- [x] 创建手动执行脚本 (scripts/manual_run.bat)
- [x] 创建删除任务脚本 (scripts/remove_tasks.bat)
- [x] 一键安装脚本 (install.bat)
- [x] 环境变量配置说明 (docs/ENV_SETUP.md)

### 6.2 使用文档 [DONE]
- [x] 完善配置文件说明 (docs/ENV_SETUP.md)
- [x] 编写使用教程 (docs/USAGE.md)
- [x] 编写故障排查指南 (docs/TROUBLESHOOTING.md)
- [x] 更新 README.md
- [x] 添加常见问题 FAQ (docs/FAQ.md)

---

## Phase 7: 增强功能 [IN_PROGRESS]

### 7.0 邮箱同步模块 [DONE]
- [x] 创建 EmailSyncManager 类（替代 BypySyncManager）
- [x] 实现 IMAP 协议连接（浙大邮箱）
- [x] 实现邮件列表获取功能
- [x] 实现附件下载功能
- [x] 实现邮件过滤规则（发件人、主题、附件类型）
- [x] 扩展数据库支持邮件元数据
- [x] 嵌套 ZIP 文件解压支持
- [x] 创建邮箱测试脚本

### 7.1 行程归类 [DONE]
- [x] 基于地理位置和日期构建行程
- [x] 多城市连续行程支持
- [x] 自动匹配打车、接送机、住宿
- [x] 未归类发票"普通打车"文件夹
- [x] 生成行程汇总报告

### 7.2 差旅费报销单自动生成 [DONE]
- [x] 基于模板文件复制报销单
- [x] 自动填写出差人信息
- [x] 自动填写出差事由、地点、日期
- [x] 自动计算并填写交通费
- [x] 市内交通费（打车+接送机）
- [x] 自动填写住宿费
- [x] 发票去重（行程单与发票只计一次）
- [x] 支持新旧文件名格式
- [x] .doc 文件处理（通过 pywin32）

### 7.3 Web 控制面板 [DONE]
- [x] 设计 Web 界面（Flask）
- [x] 查看处理记录
- [x] 手动触发任务
- [x] 配置管理界面
- [x] 待处理文件人工审核

### 7.4 统计与报表 [DONE]
- [x] 按月统计发票金额
- [x] 按出差人统计
- [x] 按发票类型统计
- [x] 导出 Excel 报表

### 7.5 智能识别增强 [DONE]
- [x] 基于历史数据的学习
- [x] 相似发票自动归类
- [x] 出差地点自动关联

---

## 任务统计

| Phase | 状态 | 任务数 | 完成 | 完成率 |
|-------|------|--------|------|--------|
| Phase 1: 项目初始化 | DONE | 11 | 11 | 100% |
| Phase 2: 基础模块 | DONE | 9 | 9 | 100% |
| Phase 3: 核心功能 | DONE | 30 | 30 | 100% |
| Phase 4: 任务调度 | DONE | 11 | 11 | 100% |
| Phase 5: 测试优化 | DONE | 27 | 27 | 100% |
| Phase 6: 部署文档 | DONE | 9 | 9 | 100% |
| Phase 7: 增强功能 | DONE | 38 | 38 | 100% |
| **总计** | | **135** | **135** | **100%** |

---

## 里程碑

| 里程碑 | 目标 | 状态 | 完成时间 |
|-------|------|------|----------|
| M1: 环境就绪 | 完成依赖安装和配置文件 | ✅ DONE | 2025-02-22 |
| M2: 核心功能完成 | 邮箱同步+OCR+解析+重命名 | ✅ DONE | 2026-03-27 |
| M3: 可运行版本 | 完整流程跑通 | ✅ DONE | 2026-03-31 |
| M4: 测试完成 | 单元测试全部通过 | ✅ DONE | 2026-04-01 |
| M5: 生产就绪 | 部署脚本和文档完善 | ✅ DONE | 2026-04-01 |
| M6: Web 控制面板 | Web 界面和管理功能 | ✅ DONE | 2026-04-01 |
| M7: 统计报表功能 | 统计分析和 Excel 导出 | ✅ DONE | 2026-04-01 |
| M8: 智能识别增强 | 基于历史的智能归类建议 | ✅ DONE | 2026-04-01 |
| M9: 集成测试 | 端到端测试和错误处理 | ✅ DONE | 2026-04-01 |

---

## 已知问题

| ID | 问题 | 优先级 | 状态 |
|----|------|--------|------|
| I1 | bypy 编码警告（GBK vs UTF-8） | P2 | 已弃用（改用邮箱） |

---

**创建时间**: 2025-02-22
**最后更新**: 2026-04-01
**当前版本**: v3.0.0 (生产就绪 - 完整版)
**状态**: ✅ 全部完成
**当前版本**: v2.3.0 (生产就绪)
**状态**: ✅ 全部完成
