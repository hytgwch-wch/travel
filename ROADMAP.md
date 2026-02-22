# ROADMAP.md - 项目任务规划

## 任务状态说明
- `[TODO]`: 待开始
- `[DOING]`: 进行中
- `[DONE]`: 已完成
- `[BLOCKED]`: 被阻塞

---

## Phase 1: 项目初始化 [DONE]

### 1.1 项目结构搭建 [DONE]
- [x] 创建目录结构（src/, config/, data/, temp/, invoices/, logs/, tests/）
- [x] 初始化 requirements.txt
- [x] 创建 .gitignore 文件
- [x] 初始化 README.md

### 1.2 配置文件创建 [DONE]
- [x] 创建 config/config.yaml（主配置）
- [x] 创建 config/parsers.yaml（发票解析规则）
- [x] 创建 config/travelers.yaml（出差人信息）

### 1.3 依赖安装 [DONE]
- [x] 安装 bypy 并完成授权
- [x] 安装 PaddleOCR 及依赖
- [x] 安装其他依赖包

---

## Phase 2: 基础模块开发 [DONE]

### 2.1 配置管理模块 (src/config.py) [DONE]
- [x] 实现配置加载类
- [x] 实现 YAML 配置解析
- [x] 配置验证逻辑

### 2.2 数据库模块 (src/database.py) [DONE]
- [x] 实现 RecordDatabase 类
- [x] 创建表结构（processed_files）
- [x] 实现 CRUD 操作接口
- [x] 添加数据库迁移支持

---

## Phase 3: 核心功能开发 [DONE]

### 3.1 百度网盘同步模块 (src/bypy_sync.py) [DONE]
- [x] 封装 bypy 命令行调用
- [x] 实现 list_remote_files() 方法
- [x] 实现 download_file() 方法
- [x] 实现 sync_new_files() 方法
- [x] 添加错误重试机制
- [ ] 单元测试

### 3.2 OCR 引擎模块 (src/ocr_engine.py) [DONE]
- [x] 初始化 PaddleOCR
- [x] 实现 recognize() 方法（图片）
- [x] 实现 recognize_pdf() 方法
- [x] 添加预处理逻辑（图片增强）
- [ ] 单元测试（使用测试图片）

### 3.3 发票解析模块 (src/parser.py) [DONE]
- [x] 实现 InvoiceType 枚举
- [x] 实现 InvoiceInfo 数据类
- [x] 实现 detect_type() 方法（类型检测）
- [x] 实现 parse() 方法（信息提取）
- [x] 编写解析规则配置（parsers.yaml）
- [x] 添加日期解析（多种格式）
- [x] 添加金额解析（多种格式）
- [x] 添加交通路线解析
- [x] 添加住宿信息解析
- [ ] 单元测试（各类发票样本）

### 3.4 文件重命名模块 (src/renamer.py) [DONE]
- [x] 实现 generate_name() 方法
- [x] 实现命名规则映射（7种发票类型）
- [x] 实现 make_unique() 方法（处理冲突）
- [x] 添加文件名合法化处理
- [ ] 单元测试

### 3.5 文件组织模块 (src/organizer.py) [DONE]
- [x] 实现 get_target_path() 方法
- [x] 实现 organize() 方法
- [x] 自动创建目标目录结构
- [x] 添加 dry_run 模式支持
- [ ] 单元测试

---

## Phase 4: 任务调度与集成 [DONE]

### 4.1 调度器模块 (src/scheduler.py) [DONE]
- [x] 实现 TaskScheduler 类
- [x] 实现 run_once() 方法（完整流程）
- [x] 实现 start_daily() 方法（定时任务）
- [x] 添加日志记录（每步操作）
- [x] 实现错误处理与恢复
- [x] 添加进度统计（TaskResult）

### 4.2 主入口脚本 [DONE]
- [x] 创建 main.py（命令行入口）
- [x] 实现命令行参数解析
  - [x] --run: 执行一次任务
  - [x] --daily: 启动定时任务
  - [x] --dry-run: 模拟运行
  - [x] --config: 指定配置文件
- [x] 添加使用帮助

---

## Phase 5: 测试与优化 [TODO]

### 5.1 集成测试 [TODO]
- [ ] 准备测试发票样本（各类型）
- [ ] 端到端测试流程
- [ ] 测试数据库持久化
- [ ] 测试文件冲突处理

### 5.2 日志与监控 [TODO]
- [ ] 配置 loguru 日志格式
- [ ] 添加文件日志（按日期滚动）
- [ ] 添加处理统计日志
- [ ] 添加错误告警机制

### 5.3 错误处理优化 [TODO]
- [ ] OCR 识别失败的处理策略
- [ ] 解析失败时的降级方案
- [ ] 网络错误的重试机制
- [ ] 添加待处理文件列表（供人工审核）

---

## Phase 6: 部署与文档 [TODO]

### 6.1 部署配置 [TODO]
- [ ] 创建 Windows 任务计划程序配置脚本
- [ ] 创建启动脚本（start.bat）
- [ ] 环境变量配置说明

### 6.2 使用文档 [TODO]
- [ ] 完善配置文件说明
- [ ] 编写使用教程
- [ ] 编写故障排查指南
- [ ] 更新 README.md

---

## Phase 7: 增强功能 [TODO]

### 7.1 Web 控制面板 [P1]
- [ ] 设计 Web 界面（Flask/FastAPI）
- [ ] 查看处理记录
- [ ] 手动触发任务
- [ ] 配置管理界面
- [ ] 待处理文件人工审核

### 7.2 统计与报表 [P1]
- [ ] 按月统计发票金额
- [ ] 按出差人统计
- [ ] 按发票类型统计
- [ ] 导出 Excel 报表

### 7.3 智能识别增强 [P1]
- [ ] 基于历史数据的学习
- [ ] 相似发票自动归类
- [ ] 出差地点自动关联

---

## 任务统计

| Phase | 状态 | 任务数 | 完成 |
|-------|------|--------|------|
| Phase 1: 项目初始化 | TODO | 9 | 0 |
| Phase 2: 基础模块 | TODO | 7 | 0 |
| Phase 3: 核心功能 | TODO | 31 | 0 |
| Phase 4: 任务调度 | TODO | 9 | 0 |
| Phase 5: 测试优化 | TODO | 12 | 0 |
| Phase 6: 部署文档 | TODO | 6 | 0 |
| Phase 7: 增强功能 | TODO | 12 | 0 |
| **总计** | | **86** | **0** |

---

## 里程碑

| 里程碑 | 目标 | 预计前置任务 |
|-------|------|-------------|
| M1: 环境就绪 | 完成依赖安装和配置文件 | Phase 1 |
| M2: 核心功能完成 | bypy同步+OCR+解析+重命名 | Phase 2 + Phase 3 |
| M3: 可运行版本 | 完整流程跑通 | Phase 4 |
| M4: 生产就绪 | 测试通过，文档完善 | Phase 5 + Phase 6 |

---

**创建时间**: 2025-02-22
**最后更新**: 2025-02-22
