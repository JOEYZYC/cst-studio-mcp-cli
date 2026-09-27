# cst-rf

**CST Studio Suite 2026.2 的本地 Python 自动化核心**，提供 `cst-rf`
命令行与 `cst-rf-mcp` MCP stdio 服务；两个前端共用工具契约、业务逻辑、
结果信封和审计。

[English](README.md) · [架构](docs/architecture.md) ·
[工具目录](docs/tool-catalog.md) · [真机验收摘要](docs/acceptance-cst-2026.2.md)

> 当前版本为 **`0.1.0.dev0` 开发预览版**。工具已注册、离线测试通过，
> 不代表其 CST History 写入或求解流程都已通过真机验收。

## 功能与验收状态

- **查看：** 按进程和工程路径核对连接身份，读取模型树、参数、边界与 Floquet
  信息；离线读取已保存的结果及本机 CST 帮助，不必启动 CST。
- **受控建模：** 将源 `.cst` 与配套数据目录复制到唯一 scratch；只接受结构化
  参数和固定 History 模板，源工程不是 live 写入目标，不暴露任意 VBA 或 shell。
- **超表面：** 设置 Floquet 模式数和入射角；依据显式选择的复数 S 通道及真实
  频率轴计算 R/T/A、PCR，导出 CSV、HTML、Touchstone。`T=0` 必须有独立的
  完整背板依据，不因透射结果缺失而自动成立。
- **求解安全：** 写模型与求解要求 `confirm=true`；写入受 `CST_WORK_DIR`、
  跨进程工程锁与追加式审计约束。无法确认的求解结果标记 `unknown`，禁止
  在同一 operation 上继续写入，不能算作成功停止。

一次周期单元胞求解、R/T/A/PCR 与部分 Floquet 设置/结果导出已通过
**CST 2026.2 真机验收**。独立有限阵列、圆极化切换、成功停止、参数扫描和
普通天线流程**尚未完成完整真机验收**。详见[公开验收摘要](docs/acceptance-cst-2026.2.md)
和[超表面阶段状态](docs/metasurface-phase-status.md)。

## 软件架构

```text
CLI / MCP stdio → 共享 ToolSpec registry → Service（schema、确认、审计、锁）
                                     ↘ 单线程 CST session → 官方 cst.interface
                                     ↘ 离线结果 / 帮助 → cst.results、FTS5
                                     ↘ 超表面计算与受控导出
```

CLI 只暴露 MCP 工具目录的**一部分**。官方 CST Python 包须通过 `PYTHONPATH`
从安装目录原位使用，不复制、不随本仓库分发。更详细的职责划分与信任边界见
[架构说明](docs/architecture.md)。

## 安装与使用（Windows）

需要 Python 3.12；live 工具还需要已安装并获授权的 CST。常见安装位置为
`C:\Program Files\CST Studio Suite 2026`；如实际安装位置不同，应修改
`CST_PATH`。本仓库不附带厂商文件或仿真数据。

```powershell
conda env create -f environment.yml
$env:CST_PATH = 'C:\Program Files\CST Studio Suite 2026'
$env:PYTHONPATH = "$env:CST_PATH\AMD64\python_cst_libraries"
$env:CST_WORK_DIR = Join-Path $HOME 'Documents\cst-rf-work'
conda run -n cst-rf-mcp cst-rf inspect status --json
conda run -n cst-rf-mcp cst-rf tools list --json
```

公开的 `environment.yml` 默认**手动连接**，不会自动启动 CST。开始任何写入
或求解之前，将 `CST_WORK_DIR` 设为私有可写目录。若本机已存在同名 conda
环境，先执行 `conda env config vars list -n cst-rf-mcp`，检查是否还保留以前
的自动启动等高风险环境变量；修改仓库文件不会自动清理运行中进程的配置。
`CST_TOOLSET` 目前**不裁剪工具**，不是权限控制机制。MCP 客户端的权限需
独立配置；不要把求解与写模型工具向不受信任的 Agent 全量开放。

## 不连接 CST 的检查

```powershell
conda run -n cst-rf-mcp ruff check .
conda run -n cst-rf-mcp ruff format --check .
conda run -n cst-rf-mcp mypy src tests
conda run -n cst-rf-mcp pytest -m "not live and not solver"
```

GitHub Actions 只跑离线检查；真实 CST 验收必须单独确认。代码来源见
[provenance](docs/provenance.md) 与[参考审查](docs/reference-audit.md)。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。本项目独立开发，不隶属或代表
Dassault Systèmes。
