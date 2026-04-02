# 环境配置说明

## 系统要求

- **操作系统**: Windows 10/11 或 Windows Server 2016+
- **Python**: 3.8 或更高版本
- **内存**: 建议 4GB 以上
- **磁盘**: 建议 500MB 以上可用空间

## 安装步骤

### 1. 安装 Python

1. 访问 [Python 官网](https://www.python.org/downloads/)
2. 下载 Python 3.8 或更高版本
3. 安装时勾选 "Add Python to PATH"

### 2. 克隆或下载项目

```bash
git clone https://github.com/your-repo/travel.git
cd travel
```

或直接下载并解压 ZIP 文件。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置文件

复制配置文件示例并根据实际情况修改：

```bash
copy config\config.yaml.example config\config.yaml
copy config\email.yaml.example config\email.yaml
```

### 5. 运行安装脚本

```bash
install.bat
```

## 环境变量

项目支持以下环境变量（可选）：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `TRavel_CONFIG_DIR` | 配置文件目录 | `./config` |
| `TRavel_DATA_DIR` | 数据文件目录 | `./data` |
| `TRavel_LOG_DIR` | 日志文件目录 | `./logs` |
| `TRavel_INVOICES_DIR` | 发票存储目录 | `./invoices` |
| `TRavel_TRIPS_DIR` | 行程目录 | `./trips` |

设置方式（临时）：

```bash
set TRavel_CONFIG_DIR=C:\path\to\config
python main.py
```

设置方式（永久）：

1. 右键"此电脑" → 属性 → 高级系统设置
2. 环境变量 → 新建
3. 输入变量名和值

## 目录结构

```
travel/
├── config/          # 配置文件
│   ├── config.yaml          # 主配置
│   ├── email.yaml           # 邮箱配置
│   ├── parsers.yaml         # 发票解析规则
│   └── travelers.yaml       # 出差人信息
├── data/            # 数据文件
│   └── records.db           # 处理记录数据库
├── logs/            # 日志文件
├── invoices/        # 下载的原始发票
├── temp/            # 临时文件
├── trips/           # 归类后的行程发票
├── src/             # 源代码
├── scripts/         # 工具脚本
├── tests/           # 单元测试
├── main.py          # 主入口
├── start.bat        # 启动脚本
└── install.bat      # 安装脚本
```

## 常见问题

### Q: pip 安装失败

**A**: 尝试使用国内镜像源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: Python 找不到命令

**A**: 确保 Python 已添加到 PATH：
1. 重新运行 Python 安装程序
2. 勾选 "Add Python to PATH"
3. 或手动添加 Python 目录到系统 PATH

### Q: 提示缺少 pywin32

**A**: 如果需要处理 .doc 文件（报销单），需安装 pywin32：

```bash
pip install pywin32
```

注意：pywin32 仅支持 Windows。

### Q: OCR 识别速度慢

**A**: PaddleOCR 首次运行会下载模型文件（约 100MB），后续运行会使用缓存。

### Q: 邮箱连接失败

**A**: 检查以下配置：
1. IMAP 服务是否开启（邮箱设置）
2. 应用密码是否正确（非登录密码）
3. 网络连接是否正常
4. 防火墙是否阻止

## 卸载

1. 删除定时任务（如已配置）：
   ```bash
   scripts\remove_tasks.bat
   ```

2. 删除项目目录

3. 删除环境变量（如已设置）
