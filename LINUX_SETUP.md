# Linux 环境配置指南

## 项目概述
Nonead Universal Robots MCP - 一个用于控制通用机器人的模型上下文协议服务器

## 系统要求

### Python 环境
- Python 版本: >= 3.10
- 推荐版本: 3.10 或 3.11

### 操作系统
- Ubuntu 20.04+ 或其他主流 Linux 发行版
- 需要网络访问权限（用于连接机器人和视觉服务器）

## 快速安装

### 1. 安装 Python 依赖

```bash
# 使用 pip 安装依赖
pip install -r requirements_linux.txt
```

### 2. 验证安装

```bash
python -c "import mcp, fastmcp, numpy, thrift, openai, sympy; print('所有依赖安装成功')"
```

## 项目结构

```
demo/
├── tools/
│   ├── io_modules/        # IO模块控制（电机、数字IO、Liyou拧螺丝机）
│   ├── robots/            # 机器人控制（UR、Duco、Dazu）
│   ├── vision/            # 视觉系统接口
│   └── algorithms/        # 算法模块
├── config/                # 配置文件（标定数据、记录点数据）
├── logs/                  # 日志工具
├── mcp_server.py          # MCP服务器入口
└── requirements_linux.txt # Linux依赖列表
```

## 配置说明

### 网络设备配置

项目需要与以下网络设备通信：

1. **IO控制器** (默认 IP: 192.168.3.21:8899)
   - 在 `tools/io_modules/io_tools.py` 中修改 `IO_CONTROLLER_IP`

2. **视觉服务器** (默认 IP: 192.168.3.198:65432)
   - 在 `tools/vision/vision_mcp_tools.py` 中修改 `VISION_IP`

3. **Liyou 拧螺丝控制器** (默认 IP: 192.168.0.10:5000)
   - 在 `tools/io_modules/device_controllers.py` 中修改 `Liyou.SERVER_IP`

4. **UR 机器人** (需要用户输入)
   - 通过 MCP 工具参数传入机器人 IP

### 配置文件位置

- 标定数据: `config/calibration/`
  - `calibration_data_ur.json` - UR 机器人标定数据
  - `calibration_data_duco.json` - Duco 机器人标定数据
  - `calibration_data_dazu.json` - Dazu 机器人标定数据
  - `tool_offset_data.json` - 工具偏移数据
  - `recorded_points_data.json` - 记录点数据
  - `nail_positions_data.json` - 钉位置数据

## 运行项目

### 启动 MCP 服务器

```bash
# 方法1: 使用 MCP CLI
mcp dev tools/mcp_server.py

# 方法2: 直接运行
python -m tools.mcp_server
```

### 与 Claude Desktop 集成

在 Claude Desktop 配置文件中添加：

```json
{
  "mcpServers": {
    "nonead-robots": {
      "command": "python",
      "args": ["-m", "tools.mcp_server"],
      "cwd": "/path/to/demo"
    }
  }
}
```

## 故障排除

### 常见问题

1. **网络连接失败**
   - 检查设备 IP 地址是否正确
   - 确认网络连通性: `ping <设备IP>`
   - 检查防火墙设置

2. **Python 版本不兼容**
   ```bash
   python --version  # 确认 >= 3.10
   ```

3. **依赖安装失败**
   ```bash
   pip install --upgrade pip
   pip install -r requirements_linux.txt --upgrade
   ```

4. **导入错误**
   - 确认在项目根目录运行
   - 检查 PYTHONPATH 设置

## 开发说明

### 日志查看
日志通过 `logs/logger_utils.py` 统一管理

### 添加新工具
参考 `tools/*/xxx_mcp_tools.py` 中的工具注册模式

### 代码风格
- 使用异步编程 (async/await)
- 类型注解 (typing)
- 全局实例管理（用于保持设备连接状态）

## 安全注意事项

1. 不要在生产环境中硬编码敏感 IP 地址
2. 使用环境变量管理配置
3. 适当设置网络隔离和访问控制

## 联系支持

如有问题，请参考项目文档或联系技术支持。
