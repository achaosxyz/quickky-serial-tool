# QSerial

**专注多会话串口调试的 Windows 桌面工具。**

[English](README.md) | [简体中文](README.zh-CN.md)

[![平台：Windows](https://img.shields.io/badge/platform-Windows-blue)](#安装)
[![Python 3](https://img.shields.io/badge/python-3-blue)](#从源码运行)
[![许可证：MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

QSerial 面向嵌入式开发者、硬件工程师和测试人员，用于连接串口设备、收发 TEXT/HEX 数据、重复发送指令并保存通信日志。它保持直接的串口操作流程：选择端口、匹配设备参数、打开连接，然后检查实际收发的数据。

## 设计理念

- **专注串口调试：** 连接、收发和日志，操作简单直接。
- **双栏多 Tab：** 独立调试多个串口，并排查看和对比会话。

## 核心功能

- **多会话调试：** 通过多个 Tab 打开不同串口，并使用双栏模式并排比较两个会话。
- **完整串口参数：** 配置端口、波特率、数据位、校验位、停止位及硬件/软件流控。
- **TEXT/HEX 收发：** 切换输入与显示模式，选择 UTF-8 或 ASCII 编码，并控制 CR、LF 或 CRLF 换行符。
- **循环与复用指令：** 按固定间隔循环发送，分组管理快捷指令，并从发送历史中重新发送成功请求。
- **接收日志：** 将通信保存到文件，可选接收时间戳，并明确提示写入、缓冲区溢出和关闭失败。
- **调试辅助：** 自动重连、自动滚动、RX/TX 计数、按端口保存草稿，以及配置导入/导出。
- **工作区适配：** Light/Dark 主题和中英文界面，默认跟随系统语言。

## 安装

### 使用 Windows 发布包

1. 从 [GitHub Releases](https://github.com/achaosxyz/quickky-serial-tool/releases) 下载最新的 `QSerial_v<版本号>.zip`。
2. 将 ZIP 解压到本地可写目录。
3. 运行 `QSerial.exe`。

发布包无需单独安装 Python。运行配置保存在 EXE 所在目录，因此请将该目录保持为可写。

### 从源码运行

环境要求：Windows、Python 3，以及已连接的串口设备或用户自行配置的虚拟串口对。

```powershell
git clone https://github.com/achaosxyz/quickky-serial-tool.git
cd quickky-serial-tool
pip3 install -r requirements.txt
.\run.bat
```

如需直接启动应用，请先生成翻译资源：

```powershell
python3 scripts/generate_translations.py
python3 src/main/app_qt.py
```

## 建立第一个串口连接

1. 连接串口设备，并在 Windows 中确认其 COM 端口。
2. 在 QSerial 的 Tab 中选择端口；再次打开端口下拉框可刷新可用端口列表。
3. 按设备要求设置波特率、数据位、校验位、停止位和流控。
4. 点击“打开串口”。连接控件和状态会反映正在打开、已连接、正在关闭及失败状态。
5. 选择接收模式，在发送编辑区输入数据，然后点击“发送”。
6. 通过 RX/TX 计数和接收区确认通信活动；需要持久记录时，请在通信前启用“保存日志文件”。

Windows 中一个 COM 端口通常同一时间只能由一个应用打开。使用 QSerial 连接前，请先关闭其他工具中的对应端口。

## 数据发送与接收

| 模式 | 适用场景 | 行为 |
| --- | --- | --- |
| TEXT | 文本指令、终端输出和可读协议 | 选择 UTF-8 或 ASCII，以及设备要求的 CR、LF 或 CRLF；QSerial 不会额外添加换行符。 |
| HEX | 二进制协议和字节级检查 | 输入准确字节，例如 `01 03 00 00 00 02`；支持空白、逗号、连字符、冒号和 `0x` 前缀。 |

- **循环发送：** 按配置的毫秒间隔重复发送当前数据；关闭或断开连接会停止循环。
- **快捷指令：** 将常用 TEXT/HEX 数据按名称分组，并发送到当前活动会话。
- **发送历史：** 仅记录成功发送的数据以便复用；失败或空数据不会记为成功历史。
- **时间戳日志模式：** 添加接收时间戳，便于检查日志中相互分离的数据段。

## 配置与日志

源码运行时，`config.json` 保存在项目根目录；发布包运行时保存在 `QSerial.exe` 所在目录。通过“文件 → 导出配置”和“文件 → 导入配置”备份或迁移设置。

如果现有配置无法读取，QSerial 会保留原文件并阻止普通写入。请导入有效配置恢复保存，避免静默覆盖损坏文件。

只有会话启用文件日志后才会写入日志。请选择可写目录，并在依赖日志记录前检查是否有日志警告。

## 问题反馈

通过 [GitHub Issues](https://github.com/achaosxyz/quickky-serial-tool/issues) 报告问题，请提供 QSerial 版本、Windows 版本、串口参数、复现步骤及已脱敏的相关日志。

## 许可证

项目代码采用 [MIT License](LICENSE)。PySide6/Qt 按 LGPLv3 使用；发布时必须保留[第三方声明](licenses/THIRD_PARTY_NOTICES.md)，并随发行物提供必要许可证文本和 Qt/PySide6 源码获取信息。
