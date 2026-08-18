# WeWrite × DeepSeek Harness

WeWrite 为 DeepSeek Harness（DSH）提供 1 个主入口和 9 个功能模块，全部采用原生
filesystem skills，同时支持 Claude Code、Codex、OpenClaw 等 Agent 环境。

DSH 会直接扫描 `$DSH_HOME/skills/<skill-name>/SKILL.md`；`DSH_HOME` 未设置时默认为
`~/.dsh`。内容工作流不需要额外的 Cordis 插件。DSH 管理工具负责安装、升级、冲突备份、
诊断和卸载，确定性能力仍由 `wewrite`
命令提供。

> DeepSeek Harness 目前处于 Developer Preview。其插件 API 可能变化；本项目优先依赖更
> 稳定的 filesystem skill 发现机制，并用 `dsh/manifest.json` 集中维护兼容清单。

## 安装

运行环境需要 Python 3.11+。推荐同时安装 `uv`，没有时安装脚本会使用 pipx 或 pip。

### Windows PowerShell

```powershell
git clone https://github.com/kingselyjoe/wewrite-dsh.git
cd wewrite-dsh
.\install-dsh.ps1
```

自定义 DSH 目录：

```powershell
.\install-dsh.ps1 -DshHome D:\agent-data\dsh
```

### macOS / Linux

```bash
git clone https://github.com/kingselyjoe/wewrite-dsh.git ~/wewrite-dsh
cd ~/wewrite-dsh
bash install-dsh.sh
```

脚本会安装两部分：

1. `wewrite` CLI，用于状态、质量检查、排版、发布和图片等确定性操作。
2. 10 个 skills，复制到 `$DSH_HOME/skills`，默认是 `~/.dsh/skills`。

也可以分步安装：

```bash
uv tool install --force .
python scripts/dsh_adapter.py install
```

Windows 默认的符号链接权限差异较大，所以 DSH 专用安装器使用复制安装。每个安装副本
都有 `.wewrite-dsh.json` 所有权标记；重复运行会安全更新。若目标已有非本工具管理的同名
目录，安装器会停止且不改文件。确认需要替换时使用 `install --force`，旧目录会先改名为
`*.backup-<UTC 时间>`，不会直接删除。

## 检查

```bash
python scripts/dsh_adapter.py doctor
```

检查项包括：

- 源仓库 manifest、版本号和 10 个 SKILL.md 是否一致；
- `$DSH_HOME/skills` 下是否完整安装；
- `wewrite` CLI 是否在 PATH；
- 是否能找到 `dsh` 或用于启动 DSH 的 `npx`。

CI 或只检查 skill 副本时可忽略 CLI：

```bash
python scripts/dsh_adapter.py --json doctor --skip-cli
```

## 启动与使用

按 DSH 官方 Developer Preview 的方式启动 Web UI：

```bash
npx @deepseek-ai/dsh web
```

在对话里直接说明要使用的能力即可，例如：

```text
使用 wewrite skill，写一篇关于 AI 编程工具的公众号文章。
使用 wewrite-topic，先给我 10 个今天可写的公众号选题。
使用 wewrite-review，检查并修改这篇文章。
使用 wewrite-rewrite，把当前文章改写成小红书图文。
```

DSH 通过 frontmatter 的 `name`、`description` 和 `user-invocable` 发现并选择模块。
原有 `allowed-tools` 字段继续保留给 Claude Code 使用；DSH 会使用自身提供的 bash、workspace、
web 和 skill 工具完成对应动作。

## 配置与数据

WeWrite 用户状态不写进 DSH skill 目录，而是放在 `$WEWRITE_HOME`，默认 `~/.wewrite`：

```bash
cp config.example.yaml ~/.wewrite/config.yaml
wewrite home
```

普通写作不需要微信公众号密钥。只有推送草稿箱时才需要在配置中提供 appid/secret，且
`wewrite-publish` 仍要求用户明确授权发布。需要生图时另配图片服务；未配置会交付提示词。

## 更新与卸载

拉取新版后重新执行安装即可：

```bash
git pull
python scripts/dsh_adapter.py install
python scripts/dsh_adapter.py doctor
```

卸载只会删除带有 WeWrite 所有权标记的 10 个目录，不碰同名的外部或手工目录：

```bash
python scripts/dsh_adapter.py uninstall
```

## 技术边界

- `dsh/manifest.json` 是 WeWrite 的 DSH skills 清单，不冒充 DSH 官方插件 manifest。
- WeWrite 的 Python runtime、内容状态和发布权限模型保持不变，降低回归风险。
- DSH filesystem provider 支持项目级 `.dsh/skills` 和用户级 `$DSH_HOME/skills`；本安装器
  默认选用户级目录，使 WeWrite 能跨项目复用。
- 若 DSH 后续稳定发布新的插件契约，只需更新 DSH 管理层，不需要重写 10 个内容模块。
