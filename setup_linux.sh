#!/bin/bash
# Linux 环境快速设置脚本

set -e  # 遇到错误时退出

echo "======================================"
echo "Robot Agent Demo - Linux 环境设置"
echo "======================================"
echo ""

# 检查 Python 版本
echo "[1/5] 检查 Python 版本..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    echo "请安装 Python 3.10 或更高版本"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo "检测到 Python 版本: $PYTHON_VERSION"

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "警告: Python 版本低于 3.10，建议升级"
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查 pip
echo ""
echo "[2/5] 检查 pip..."
if ! command -v pip3 &> /dev/null; then
    echo "错误: 未找到 pip3"
    echo "请安装 pip: sudo apt install python3-pip"
    exit 1
fi

# 升级 pip
echo "升级 pip 到最新版本..."
pip3 install --upgrade pip --user

# 安装依赖
echo ""
echo "[3/5] 安装 Python 依赖..."
pip3 install -r requirements_linux.txt

# 验证安装
echo ""
echo "[4/5] 验证安装..."
python3 -c "
import sys
try:
    import mcp
    import fastmcp
    import numpy
    import thrift
    import openai
    import sympy
    print('✓ 所有依赖安装成功')
    sys.exit(0)
except ImportError as e:
    print(f'✗ 依赖安装失败: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "依赖验证失败，请检查安装过程"
    exit 1
fi

# 创建环境配置文件
echo ""
echo "[5/5] 创建环境配置文件..."
if [ ! -f .env ]; then
    cp .env.template .env
    echo "✓ 已创建 .env 文件，请根据实际情况修改配置"
else
    echo "ℹ .env 文件已存在，跳过创建"
fi

# 完成
echo ""
echo "======================================"
echo "✓ 环境设置完成！"
echo "======================================"
echo ""
echo "下一步操作:"
echo "1. 修改 .env 文件中的设备 IP 地址"
echo "2. 启动 MCP 服务器: python3 -m tools.mcp_server"
echo "3. 或使用 MCP CLI: mcp dev tools/mcp_server.py"
echo ""
echo "详细配置说明请参考: LINUX_SETUP.md"
