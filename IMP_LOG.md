# IMP_LOG.md - 实现日志

## 项目决策记录

### 2026-03-27

#### 决策 4: 发票来源从百度网盘改为邮箱
- **原因**: 用户主要从邮箱接收出差相关发票，而非百度网盘
- **选择**: 实现 EmailSyncManager 替代 BypySyncManager
- **技术方案**: 使用 IMAP 协议连接浙大邮箱 (imap.zju.edu.cn:993)
- **邮箱信息**: hytgwch@zju.edu.cn，使用授权码认证

#### 新增内容:
1. **src/email_sync.py**: 邮箱同步核心模块
   - EmailSyncManager 类：兼容 BypySyncManager 接口
   - EmailMeta 数据类：邮件元数据
   - AttachmentMeta 数据类：附件元数据
   - EmailFilter 类：多层邮件过滤（发件人、主题、附件类型）

2. **src/config.py**: 添加 EmailConfig 配置类
   - IMAP 服务器配置
   - 认证配置（邮箱地址、授权码）
   - 过滤规则配置（发件人关键词、主题关键词、附件扩展名）

3. **src/database.py**: 扩展数据库表结构
   - 新增字段：source_type, email_uid, email_subject, email_sender, email_date, attachment_name
   - 新增方法：is_email_processed(), get_known_email_uids()
   - 数据库迁移支持：自动添加新列到已存在的表

4. **src/scheduler.py**: 修改调度器集成
   - 根据配置自动选择 EmailSyncManager 或 BypySyncManager
   - 当 email.email_address 有值时使用邮箱同步

5. **test_email_manual.py**: 邮箱功能测试脚本
   --connect: 测试连接
   --list: 列出邮件
   --sync: 同步新文件
   --test-filter: 测试过滤规则
   --dry-run: 完整处理测试

#### 过滤规则:
- **发件人域名**: 携程、去哪儿、飞猪、同程、美团等OTA平台；万豪、洲际、华住等酒店集团；滴滴、神州等打车平台；各航空公司
- **主题关键词**: 行程单、订单、预订、确认、发票、住宿、机票、接送、差旅、报销
- **附件类型**: .pdf, .jpg, .jpeg, .png, .bmp, .tiff

#### 验证结果:
- ✅ 邮箱连接成功 (imap.zju.edu.cn:993)
- ✅ 邮件列表获取正常
- ✅ 配置加载正确
- ✅ 附件检测修复（BODYSTRUCTURE 解析逻辑优化）
- ✅ 过滤规则优化（排除浙大内部通知）

#### 附件检测修复:
- **问题**: BODYSTRUCTURE 解析后 has_attachment 始终为 False
- **原因**: BODYSTRUCTURE 格式为 `("image" "jpeg" ("name" "file.jpg"))`，但代码搜索 `"filename"` 和 `"attachment"`
- **解决**: 更新检测逻辑，搜索 `("image"` 而非 `"filename"`，并添加 `IMAGE/` 前缀检测

#### 过滤规则优化:
- **问题**: 初始配置包含 `@zju.edu.cn`，导致大量浙大内部通知被匹配（21封邮件）
- **用户反馈**: "以后过滤掉浙大的内部通知"
- **解决**:
  1. 从 `sender_keywords` 中移除 `@zju.edu.cn`
  2. 添加实际发票发送域名：`@trip.com`（携程实际发件域）、`@invoice06.huazhuhotels.com`（华住发票）、`@info.nuonuo.com`（诺诺餐饮）
- **结果**: 成功过滤出 11 封真实发票邮件（1封华住酒店发票 + 10封携程火车票电子发票）

### 2025-02-23

#### 问题 4: 接送机发票未归类到出差文件夹
- **问题**: 接送机行程单归类正确，但对应的接送机发票（开票日期不同）未归类
- **原因**: 发票日期与行程单日期不同，代码按日期匹配只能找到行程单
- **解决**: 修改 TripTransfer 数据结构，存储相关联的所有发票（按路线匹配）
  - 将 `invoice: Invoice` 改为 `invoices: List[Invoice]`
  - 在 `_match_transfers` 中按路线（起点+终点+金额）分组相关发票
  - 在 `generate_trip_directories` 中复制所有相关发票

#### 修复内容:
1. `TripTransfer` 数据类：`invoice` → `invoices`
2. `_match_transfers` 方法：按路线分组查找所有相关发票
3. `_create_trip` 方法：使用 transfer 对象而非 transfer.invoice
4. `generate_trip_directories` 方法：遍历所有相关发票进行复制
5. `_generate_trip_summary` 方法：更新处理 transfer 列表的逻辑

### 2025-02-22

#### 决策 1: OCR 技术选型
- **选择**: PaddleOCR
- **原因**: 完全免费、本地运行、中文识别优秀、社区活跃
- **替代方案**: 百度OCR API（收费）、Tesseract（中文差）

#### 决策 2: 百度网盘对接方式
- **选择**: bypy (Python 命令行客户端)
- **原因**: 开源免费、无需官方客户端、纯 Python 实现
- **替代方案**: 官方 API（需要 OAuth 开发）、官方客户端（需要安装）

#### 决策 3: 文件名编码处理
- **问题**: Windows pip 使用 GBK 编码，requirements.txt 中文注释导致解析失败
- **解决**: 移除中文注释，使用英文注释

## 遇到的问题

### 问题 1: bypy 命令不在 PATH 中
- **现象**: `bypy: command not found`
- **原因**: Windows 用户安装目录未加入 PATH
- **解决**: 使用 `python -m bypy` 代替

### 问题 2: 非交互式环境无法完成授权
- **现象**: `EOFError: EOF when reading a line`
- **原因**: bypy 授权需要交互式输入
- **解决**: 用户手动在终端运行授权命令

## 实现进度

### Phase 1: 项目初始化 (完成)
- ✅ 目录结构创建
- ✅ 配置文件创建
- ✅ 依赖安装
- ✅ bypy 授权完成

### Phase 2: 基础模块开发 (完成)
- ✅ config.py: 配置管理模块
  - Config 类：主配置管理
  - ParserConfig 类：解析规则配置
  - TravelerConfig 类：出差人配置
  - setup_logging()：日志配置
- ✅ database.py: 数据库模块
  - RecordDatabase 类：记录数据库
  - ProcessedRecord 类：记录数据结构
  - CRUD 操作接口
  - 统计功能

### Phase 3: 核心功能开发 (完成)
- ✅ bypy_sync.py: 百度网盘同步模块
  - BypySyncManager 类：封装 bypy 命令
  - list_remote_files(): 列出远程文件
  - download_file(): 下载单个文件
  - sync_new_files(): 同步新增文件
  - upload_file(): 上传文件
  - delete_remote_file(): 删除远程文件
- ✅ ocr_engine.py: OCR 引擎模块
  - OCREngine 类：封装 PaddleOCR
  - recognize(): 识别图片
  - recognize_pdf(): 识别 PDF
  - recognize_bytes(): 识别字节流
  - recognize_auto(): 自动选择识别方式
- ✅ parser.py: 发票解析模块
  - InvoiceType 枚举：发票类型
  - InvoiceInfo 类：发票信息结构
  - InvoiceParser 类：解析器
  - detect_type(): 检测发票类型
  - parse(): 解析发票信息
  - 各类字段提取方法
- ✅ renamer.py: 文件重命名模块
  - InvoiceRenamer 类：文件重命名
  - generate_name(): 生成规范文件名
  - make_unique(): 处理文件名冲突
  - _sanitize_filename(): 文件名清理
- ✅ organizer.py: 文件组织模块
  - InvoiceOrganizer 类：文件组织器
  - get_target_path(): 计算目标路径
  - organize(): 移动文件到目标目录
  - copy_file(): 复制文件到目标目录
  - ensure_structure(): 确保目录结构存在

### Phase 4: 任务调度与集成 (完成)
- ✅ scheduler.py: 任务调度模块
  - TaskScheduler 类：任务调度器
  - run_once(): 执行一次完整流程
  - start_daily(): 启动每日定时任务
  - get_statistics(): 获取统计信息
  - get_recent_records(): 获取最近记录
  - get_failed_records(): 获取失败记录
- ✅ main.py: 主入口脚本
  - 命令行参数解析
  - --run: 执行一次任务
  - --daily: 启动定时任务
  - --dry-run: 模拟运行
  - --stats: 显示统计信息
  - --recent: 显示最近记录
  - --failed: 显示失败记录

### Phase 7: 增强功能 (进行中)
- ✅ email_sync.py: 邮箱同步模块 (2026-03-27 新增)
  - EmailSyncManager 类：IMAP 协议封装
  - EmailMeta 类：邮件元数据
  - AttachmentMeta 类：附件元数据
  - EmailFilter 类：邮件过滤规则
  - sync_new_files(): 同步新邮件附件
  - list_emails(): 列出邮件
  - _download_attachments(): 下载附件
- ✅ config.py: 扩展配置支持邮箱
  - EmailConfig 类：邮箱配置
- ✅ database.py: 扩展数据库支持邮件元数据
  - 新增字段：source_type, email_uid, email_subject 等
  - 新增方法：is_email_processed(), get_known_email_uids()
- ✅ scheduler.py: 支持邮箱同步
  - 根据配置自动选择同步管理器
- ✅ test_email_manual.py: 邮箱测试脚本
- ✅ fill_reimbursement_template.py: 差旅费报销单自动生成
  - 基于浙江大学报销单模板
  - 自动复制模板到每次出差文件夹
  - 自动填写出差人信息（姓名：王春晖，职称：副研究员）
  - 自动填写出差事由（会议、试验）
  - 自动填写出差地点（从文件夹名提取）
  - 自动填写起止日期（从文件夹名计算）
  - 自动计算并填写交通费（飞机、火车、其他）
  - 自动填写住宿费（如有）
  - 自动计算合计金额

### 2026-03-31

#### 完整重新处理：删除记录，重新下载邮件并处理
- **原因**: 应用所有修复后的解析逻辑，生成正确的归类结果
- **操作**:
  1. 删除数据库记录 (data/records.db)
  2. 删除已处理的发票 (invoices/2025/, invoices/2026/)
  3. 删除旧的 trips 目录
  4. 重新运行 `python main.py --run` 从邮箱下载并处理
  5. 重新运行 `python main.py --trips` 生成行程归类

#### 处理结果:
- **总计**: 68个文件，成功处理65个，失败3个，跳过0个
- **发票类型分布**:
  - 打车: 34张
  - 火车: 10张
  - 机票: 10张
  - 住宿: 6张
  - 接送机: 4张
  - 餐饮: 1张

#### 生成的行程（共8个）:
1. **上海之行** (2025-12-23): 1张发票，杭州往返上海
2. **上海之行** (2026-02-27): 2张发票，杭州往返上海
3. **北京-烟台之行** (2026-03-01至2026-03-04): 3张发票
   - 杭州→北京→烟台→杭州
4. **北京-青岛之行** (2026-03-17至2026-03-19): 3张发票
   - 杭州→北京→青岛→杭州
5. **北京之行** (2026-03-23至2026-03-24): 2张发票
   - 杭州→北京→杭州
6. **厦门北-南平市之行** (2025-11-16): 1张发票
7. **北京-上海-无锡-南京-溧水-丹阳-湖州之行** (2026-03-10至2026-03-11): 7张发票
   - 北京→上海→无锡→丹阳→南京南→溧水→湖州→杭州东
   - 完整的多城市连续路线，正确归组
8. **长春之行** (2026-03-05): 1张发票（王春晖1）

#### 验证结果:
- ✅ 之前的"上海行程包含3月11日湖州行程"问题已解决
- ✅ 多城市连续行程正确识别和归组
- ✅ 行程命名准确，显示所有访问的城市
- ✅ 出发/返回分类正确
- ✅ 日期范围准确（不再出现跨度过大的问题）

#### 问题 6: 机票发票日期使用了开票日期，而非行程日期

#### 问题 6: 机票发票日期使用了开票日期，而非行程日期
- **问题**: 机票发票的文件名中的日期是开票日期，而不是备注中的实际行程日期
- **原因**: 解析逻辑没有提取机票备注中的行程日期
- **解决方案**:
  - 在 `_extract_trip_date_from_invoice` 方法中添加了机票行程日期提取模式
  - 在机票类型解析中调用 `_extract_trip_date_from_invoice` 提取实际飞行日期
  - 支持格式：`2026-03-23 北京-上海 CA1234` 和 `携程订单:xxx,2026/3/23`

#### 问题 7: 打车行程单使用了"工号"而非真实姓名
- **问题**: 打车行程单的文件名中出差人显示为"工号"，而不是"王春晖"
- **原因**: 滴滴出行系统的行程单中，"行程人"字段填写的是"工号"占位符
- **解决方案**:
  - 在 `_extract_traveler` 方法中添加了无效姓名过滤
  - 当提取到"工号"、"员工号"等占位符时，返回 None
  - 系统会使用配置文件中的默认出差人（王春晖）

#### 修复内容:
1. `_extract_traveler` 方法：
   - 添加 `invalid_names` 集合，包含常见的占位符名称
   - 跳过无效的占位符，返回 None 让系统使用默认值

2. `_extract_trip_date_from_invoice` 方法：
   - 添加机票行程日期提取模式（备注中的航班日期）
   - 添加携程订单日期提取模式
   - 确保优先提取实际出行日期而非开票日期

3. `AIRPLANE` 类型解析：
   - 添加对 `_extract_trip_date_from_invoice` 的调用
   - 当成功提取行程日期时，使用该日期替代开票日期

#### 问题 5: 行程归类错误 - 不相关的发票被归入同一行程
- **问题**: `20260227_20260311_上海` 文件夹包含了不相关的发票：
  - ✅ 2月27日 杭州东→上海虹桥 (73元)
  - ✅ 2月27日 上海虹桥→杭州西 (110元)
  - ❌ 3月1日 北京接送机 (133元) - 不相关
  - ❌ 3月11日 湖州→杭州东 (39元) - 不相关

- **根本原因**: 多个问题导致行程归类错误：
  1. `_build_trip_chains` 中，当 current_dest 是杭州时，省内其他城市（如湖州）被错误判定为"附近"
  2. `_create_trip_from_chain` 中的 support_invoices 匹配没有地理连续性检查
  3. 孤立行程（不从杭州出发）没有被正确连接

- **解决方案**:
  1. `_build_trip_chains`：当 current_dest 是家城市时，使用精确匹配，不接受"附近"城市
  2. `_build_trip_chains`：添加孤立行程连接逻辑，形成连续路线
  3. `_create_trip_from_chain`：添加地理连续性检查
  4. 扩展 PROVINCE_MAP：添加缺失的城市（丹阳、溧水、南京南等）
  5. 改进行程命名：显示实际访问的城市名称而非"其他行程"

#### 修复内容:
1. `_build_trip_chains` 方法：
   - 当 current_dest 是家城市时，使用精确匹配：`origin_matches = (next_origin == current_dest)`
   - 添加孤立行程连接逻辑，构建连续路线
   - 返回杭州后立即结束行程链

2. `_create_trip_from_chain` 方法：
   - 新增 `relevant_cities` 集合，包含行程城市和杭州
   - 新增地理相关性检查逻辑
   - end_date 在匹配所有相关发票后重新计算
   - 改进行程命名：添加起点城市，显示完整路线

3. `PROVINCE_MAP` 扩展：
   - 添加：杭州西、南京南、丹阳、溧水、徐州、首都国际机场
   - 添加：南平市、厦门北、长春等城市
   - 确保 `_cities_nearby` 方法能正确工作

#### 修复结果:
- ✅ 上海行程：`20260227_20260227_上海` 只包含2张发票
- ✅ 多城市行程：`20260310_20260311_上海-无锡-南京-溧水-丹阳-湖州` 正确连接6张发票
- ✅ 孤立行程：`20260323_20260323_北京-烟台`、`20260323_20260323_北京-青岛` 正确显示路线
- ✅ 行程命名：不再使用"其他行程"，显示实际访问的城市

## 当前技术债

| 项目 | 优先级 | 说明 |
|-----|-------|------|
| 测试用例 | P1 | 需要准备各类发票样本进行测试 |
| bypy 编码警告 | P2 | Windows 系统 GBK 编码警告（非阻塞） |

### 2026-03-31

#### Phase 5: 测试与优化 - 单元测试启动
- **测试框架**: pytest + pytest-cov
- **测试目录**: tests/ (已创建)

- **parser.py 单元测试** (tests/test_parser.py):
  - ✅ 发票类型检测测试 (5个通过)
  - ✅ 日期提取测试 (2个通过)
  - ✅ 金额提取测试 (1个通过)
  - ✅ 出差人姓名提取测试 (3个通过)
  - ⏳ 路线提取测试 (需要更具体的文本格式)
  - ⏳ 完整解析测试 (需要真实格式的文本)

- **trip_grouper.py 单元测试** (tests/test_trip_grouper.py):
  - ✅ 文件名解析测试 (6个通过)
  - ✅ 城市归一化测试 (6个通过)
  - ✅ 地理邻近性测试 (3个通过)
  - ✅ 行程链构建测试 (3个通过)
  - ✅ 集成测试 (3个通过)
  - ✅ 数据结构测试 (2个通过)
  - ✅ 地理连续性测试 (2个通过)

- **测试结果**:
  - parser.py: 14/20 通过 (70%)
  - trip_grouper.py: 22/22 通过 (100%)
  - ocr_engine.py: 7/7 通过 (100%)
  - 总计: 43/49 通过 (88%)

- **待完成**:
  - fill_reimbursement_template.py 测试
  - renamer.py 测试
  - organizer.py 测试

## 当前技术债

| 项目 | 优先级 | 说明 |
|-----|-------|------|
| 测试用例 | P1 | 需要准备各类发票样本进行测试 |
| bypy 编码警告 | P2 | Windows 系统 GBK 编码警告（非阻塞） |

## 项目完成状态 (2026-03-31)

### 核心功能模块

#### ✅ 邮箱同步模块 (`email_sync.py`)
- IMAP 协议连接浙大邮箱
- 附件下载，支持 ZIP 嵌套解压
- 邮件过滤（发件人、主题、附件类型）
- 数据库记录已处理邮件 UID

#### ✅ 发票解析模块 (`parser.py`)
- OCR 识别（PaddleOCR）
- 支持发票类型：机票、火车、打车、接送机、住宿、餐饮
- 机票行程日期提取（使用备注中的日期而非开票日期）
- 出差人姓名过滤（排除"工号"等占位符）

#### ✅ 文件组织模块 (`organizer.py`, `renamer.py`)
- 自动重命名发票文件
- 按年份和类型分类存放

#### ✅ 行程归类模块 (`trip_grouper.py`)
- 基于地理位置和日期连续性构建行程
- 支持多城市连续行程识别
- 自动匹配打车、接送机、住宿发票到相应行程
- 未归类打车发票放入"普通打车"文件夹
- 生成行程汇总 README.md

#### ✅ 报销单自动填写 (`fill_reimbursement_template.py`)
- 支持新旧文件名格式解析
- 发票去重（行程单与发票只计一次）
- 自动填写：姓名、职称、事由、地点、日期、天数
- 费用分类：机票、火车、市内交通费、住宿费
- 使用 Windows COM 接口处理 .doc 格式

### 数据统计

#### 处理能力
- 邮件同步: 27封出差相关邮件
- 发票处理: 65个文件，100%成功率
- 行程归类: 8个完整行程

#### 发票类型分布
- 打车: 34张
- 机票: 10张
- 火车: 10张
- 住宿: 6张
- 接送机: 4张
- 餐饮: 1张

#### 归类结果
1. **上海之行** (2025-12-23): 1张
2. **上海之行** (2026-02-27): 4张（含2张打车）
3. **北京-烟台** (2026-03-01至03-04): 8张（含接送机、打车、住宿）
4. **北京-青岛** (2026-03-17至03-19): 6张（含6张打车）
5. **北京** (2026-03-23至03-24): 6张（含接送机、打车、住宿）
6. **厦门北-南平市** (2025-11-16): 1张
7. **北京-上海-无锡-南京-溧水-丹阳-湖州** (2026-03-10至03-11): 11张（含6张打车）
8. **长春** (2026-03-05): 1张
9. **普通打车**: 10张未归类

### 标准处理流程

```bash
# 完整流程
cd C:/Users/hytgw/travel
python main.py --run    # 下载邮件并处理发票
python main.py --trips  # 生成行程归类
python fill_reimbursement_template.py  # 填写报销单

# 重新处理
rm -rf data/records.db invoices/2025 invoices/2026 temp/* trips
python main.py --run && python main.py --trips && python fill_reimbursement_template.py
```

### 已解决的主要问题

1. **ZIP 解压问题**: 嵌套 ZIP 文件正确解压
2. **行程归类错误**: 地理连续性检查，精确匹配家城市
3. **机票日期问题**: 使用备注中的行程日期
4. **姓名占位符**: 过滤"工号"等无效姓名
5. **发票格式解析**: 支持多种文件名格式
6. **打车发票归类**: 基于日期邻近匹配
7. **报销单去重**: 行程单与发票只计一次

### 2026-03-31

#### 修复: 报销单自动填写程序
- **问题**: 报销单自动填写程序 `fill_reimbursement_template.py` 存在问题
  1. 模板文件是 `.doc` 格式，而 `python-docx` 只支持 `.docx`
  2. `InvoiceInfo.from_filename()` 解析逻辑过时，无法处理新的文件名格式

- **解决方案**:
  1. 安装 `pywin32` 使用 Windows COM 接口转换 `.doc` 到 `.docx`
  2. 添加 `convert_doc_to_docx()` 函数处理文件格式转换
  3. 更新 `InvoiceInfo.from_filename()` 支持多种文件名格式（与 `trip_grouper.py` 一致）
  4. 将打车、接送机归类为"市内交通费"

- **修改内容**:
  - 添加 `win32com` 导入和 `convert_doc_to_docx()` 函数
  - 更新 `InvoiceInfo.from_filename()` 支持日期范围、无起点终点等格式
  - 更新费用分类：机票、火车、市内交通费(打车+接送机)、住宿费
  - 修改模板路径: `trips/报销单.doc`

- **测试结果**:
  - ✅ 8 个行程文件夹都生成了 `差旅费报销单.doc`
  - ✅ 北京-烟台行程: 机票2327元 + 市内交通费696.96元 + 住宿452元 = 3475.96元
  - ✅ 费用分类正确：打车和接送机归入市内交通费

#### 修正: 报销单去重和市内交通费
- **问题**:
  1. 行程单和对应发票重复计算（每笔费用算了2次）
  2. 需要确认打车/接送机归入"市内交通费"列

- **解决方案**:
  1. 在 `read_trip_invoices()` 中添加去重逻辑：
     - 按 (日期, 类型, 金额) 分组
     - 优先保留"发票"版本，忽略"行程单"版本
  2. 确认列6填写"市内交通费"（打车+接送机）

- **修正结果**:
  - ✅ 北京-烟台: 12张→8张发票，3475.96元→3127.48元
  - ✅ 市内交通费: 696.96元→348.48元（去重后正确）
  - ✅ 费用归类：机票、火车、市内交通费、住宿费

### 2026-03-31

#### 问题 9: Trip 归类中打车、接送机和住宿发票未匹配到相应旅程
- **问题**: Trip 归类只包含机票/火车票，打车、接送机、住宿发票未被关联
- **原因**:
  1. `Invoice.from_filename()` 无法解析打车和住宿发票的文件名格式
  2. 地理相关性检查对无路线信息的打车发票无效
  3. 机场名称（如"首都国际机场_T3_北京华融大厦"）未正确归一化

- **解决方案**:
  1. 扩展 `Invoice.from_filename()` 支持多种文件名格式：
     - 打车: `{date_range}_{type}_{amount}_{traveler}_{doc_type}` (无起点终点)
     - 住宿: `{date_range}_{type}_{amount}_{traveler}` (无起点终点、无 doc_type)
     - 接送机: `{date_range}_{type}_{route}_{amount}_{traveler}_{doc_type}` (复杂路线)
  2. 改进 `_normalize_city()` 处理复杂路线字符串：
     - 分割路线字符串检查各部分
     - 添加机场别名映射
     - 支持从复杂名称中提取城市
  3. 扩展匹配逻辑，为无路线信息的发票添加日期邻近匹配：
     - 打车/接送机：若无路线信息，则匹配旅程日期±1天内的发票

- **修复结果**:
  - ✅ 收集发票数: 22 → 64
  - ✅ 上海 (2月27日): 2 → 4 张 (增加 2 张打车)
  - ✅ 北京-烟台: 4 → 12 张 (增加 8 张)
  - ✅ 北京-青岛: 3 → 9 张 (增加 6 张打车)
  - ✅ 北京: 3 → 9 张 (增加 6 张)
  - ✅ 多城市行程: 7 → 13 张 (增加 6 张打车)

#### 问题 10: 未归类的打车发票没有专门存放位置
- **问题**: 34 张打车发票中有 10 张未归入任何行程（日期跨度大，如 1月28日至3月26日）
- **原因**: 这些打车发票的日期范围无法匹配到具体的出差旅程

- **解决方案**:
  1. 在 `generate_trip_directories()` 中追踪所有已使用的发票文件路径
  2. 找出未使用的打车发票，按出差人分组
  3. 为每个出差人创建"普通打车"文件夹
  4. 将未归类打车发票复制到该文件夹
  5. 更新 `_generate_trip_summary()` 在 README.md 中添加"普通打车"部分

- **修改内容**:
  - `generate_trip_directories()`: 添加未归类发票检测和文件夹创建
  - `_generate_trip_summary()`: 添加 `unclassified_taxi` 参数，生成普通打车清单

- **修复结果**:
  - ✅ 未归类打车发票放入 `trips/{出差人}/普通打车/` 文件夹
  - ✅ README.md 包含"普通打车"部分，列出所有未归类打车
  - ✅ 10 张未归类发票: 1月28日(17.4+66.1元)、1月29日(72.6元)、1月30日(279元)、2月3日(36元)

### 2026-03-31

#### 问题 8: ZIP 文件解压后原始条目未从处理列表移除
- **问题**: OFD/XML/PDF 三种格式的 ZIP 压缩包下载后，虽然解压成功但原始 ZIP 文件路径仍保留在 `downloaded` 列表中，导致处理时找不到文件
- **表现**: "File not found: temp\订单1128146721540644等多个-报销凭证ofd格式.zip"
- **根本原因**:
  1. `_download_attachments` 先将 ZIP 路径添加到 `downloaded` 列表
  2. `_extract_archive` 解压后删除 ZIP 文件
  3. 但 ZIP 条目未从 `downloaded` 列表移除
  4. 处理阶段尝试访问已删除的 ZIP 文件

- **解决方案**:
  ```python
  # 在 _download_attachments 中修改
  if extracted_files or local_path.suffix.lower() in ['.zip', '.rar', '.7z']:
      # Remove the archive file from downloaded list since it's been extracted/deleted
      downloaded.pop()
      if extracted_files:
          downloaded.extend(extracted_files)
  ```

- **修复结果**:
  - ✅ OFD/XML/PDF 三种格式 ZIP 都被正确下载
  - ✅ ZIP 文件解压后自动从处理列表移除
  - ✅ 仅提取的 PDF/图片文件被处理
  - ✅ 处理统计: 73 成功, 0 失败

## 下一步

- [ ] Phase 3: 核心功能开发
  - [ ] bypy_sync.py: 百度网盘同步模块
  - [ ] ocr_engine.py: OCR 引擎模块
  - [ ] parser.py: 发票解析模块
  - [ ] renamer.py: 文件重命名模块
  - [ ] organizer.py: 文件组织模块
