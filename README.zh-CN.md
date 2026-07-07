# skill-sync

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/version-0.3.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs welcome">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <b>简体中文</b> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

**用 Git 统一管理本地所有 AI Agent 使用的 Skills，作为唯一源码。**

如今的 AI Agent —— Claude Code、Codex、Cursor、Gemini CLI、Copilot、Windsurf、
WorkBuddy 等 —— 都支持 [Skills](https://www.anthropic.com/news/skills)（`SKILL.md`
目录），但每个 Agent 的存放位置都不一样。在一个 Agent 里装了某个 skill，其它 Agent
就没有；在一个 Agent 里改了，其它副本就会不一致。

`skill-sync` 解决了这个问题。它把每个 skill 的唯一副本集中放在 [`skills/`](skills/)
下，再用**软链接**让每个已安装的 Agent 都指向它。在这里改一次，所有 Agent 同步更新；
只在一个 Agent 里装的 skill，下次同步就会共享给其它所有 Agent。

```
             ┌─────────────────────────────┐
             │   skills/  (本仓库, Git 管理)  │   ← 唯一的源码
             └──────────────┬──────────────┘
        ┌───────────┬───────┼───────┬───────────┐
      软链接      软链接    软链接   软链接      软链接
        ▼           ▼        ▼       ▼           ▼
   ~/.claude/   ~/.codex/  ~/.cursor/ ~/.gemini/  … 每个已安装的 Agent
```

## 功能特性

- **收集 + 全量镜像** —— 从每个 Agent 收集源码安装的 skill 到仓库，再把所有 skill
  软链回每个 Agent，保证完全一致。
- **只处理已安装的 Agent** —— 自动探测本机装了哪些 Agent；不会为没装的 Agent 创建目录。
- **首次选择** —— `init` 让你挑选要管理哪些 Agent（或全选）。
- **自动同步** —— 用 `schedule --interval 1h` 安装原生系统定时任务，或用前台 `watch`
  循环；按计划自动同步，可选自动 commit/push。
- **跨平台** —— 支持 macOS、Linux、Windows（Windows 在无符号链接权限时改用目录 junction）。
- **安全** —— 默认 dry-run；绝不覆盖真实目录；内容冲突只报告、绝不自动处理；删除的
  重复项会备份；幂等。

## 安装

### 方式一 —— 让 AI Agent 一键安装（复制粘贴即可）

复制下面这段，粘贴给任意 AI Agent（Claude Code、Codex、Cursor…），它就会克隆仓库、
探测你已安装的 Agent 并完成同步：

```text
帮我安装 “skill-sync”——它能把我本地所有 AI Agent 的 Skills 用一个 Git 仓库统一同步。

1. 如果 ~/skill-sync 不存在，执行：
   git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
2. 预览同步（自动探测我已安装的 Agent，不改动任何东西）：
   python3 ~/skill-sync/bin/skill-sync.py init --all
3. 把计划展示给我。如果没有冲突，就执行：
   python3 ~/skill-sync/bin/skill-sync.py --apply
4. 告诉我探测到哪些 Agent，现在共享了多少个 skill。

需要 Python 3.9+。不要覆盖我已有的 skill——如果同名 skill 内容不同，停下来让我确认。
```

> **提示：** 装好后，以后只需对任意 Agent 说一句 *“同步我的 skills”* 即可再次同步
> —— `skill-sync` 技能已镜像进每个 Agent，无需记任何命令。

### 方式二 —— 手动安装

除 **Python 3.9+** 外无任何依赖。克隆即用：

```bash
git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
cd ~/skill-sync
python3 bin/skill-sync.py --version
```

也可选装 `skill-sync` 命令（`pip install -e .`）。若安装后 skills 仓库在别处，用
`export SKILL_SYNC_HOME=~/my-skills` 指向它。

## 快速开始

```bash
# 1. 选择要管理哪些已安装的 Agent（交互式，或 --all）
python3 bin/skill-sync.py init

# 2. 预览一次同步会做什么（不改动任何东西）
python3 bin/skill-sync.py

# 3. 执行
python3 bin/skill-sync.py --apply

# 4. 提交并推送（本仓库是唯一源码）
git add -A && git commit -m "sync skills" && git push
```

## 命令

| 命令 | 作用 |
|---|---|
| `init [--all\|--agents a,b]` | 探测已安装 Agent，选择要管理的，保存配置并同步 |
| `sync [--apply]` | 收集 + 镜像。不加 `--apply` 为 dry-run |
| `status` | 平台、Agent 表、自动同步状态，以及一次 dry-run 概览 |
| `list` | 列出所有已知 Agent 及其安装/纳管状态 |
| `watch --interval 10m` | 前台循环，按间隔同步 |
| `schedule --interval 1h` | 安装原生系统定时任务（launchd / 任务计划 / systemd） |
| `unschedule` | 移除定时任务 |
| `update [--check]` | 更新工具到最新版本（git pull） |
| `backup [--set URL]` | 把你的 skills 备份到你自己的 Git 仓库（默认关闭） |

常用 `sync` 参数：`--adopt-external`（收编当前软链到外部目录的 skill）、`--agent NAME`
（限定某些 Agent）、`--commit --push`（执行后自动 git）、`--json`、`--no-backup`。

### 自动同步

```bash
# 每小时后台同步一次，自动 commit+push，重启后仍生效
python3 bin/skill-sync.py schedule --interval 1h

# 或前台简单循环
python3 bin/skill-sync.py watch --interval 10m
```

间隔支持 `s`/`m`/`h`/`d`（如 `90s`、`10m`、`1h`、`12h`、`24h`、`1d`）；纯数字表示
分钟。最小 `30s`。日志写入 `~/.skill-sync/autosync.log`。

### 更新与备份

```bash
# 更新 skill-sync 到最新版本
python3 bin/skill-sync.py update            # 或：update --check

# 让每次定时任务先自更新
python3 bin/skill-sync.py schedule --interval 1h --auto-update

# 把你的 skills 备份到你自己的 Git 仓库（默认关闭）
python3 bin/skill-sync.py backup --set git@github.com:you/my-skills-backup.git
python3 bin/skill-sync.py backup            # 手动推送；定时同步后也会自动推送
```

`update` 会 fast-forward，或在你本地的 skill 提交之上 rebase。`backup` 推送到你自己
掌控的第二个 Git 远程 —— 当你从上游克隆本工具、又想把自己的 skills 单独存一份时很有用。

## 同步原理

1. **收集** —— 扫描每个 Agent 的 skills 目录，找出**真实目录**（忽略软链接）且含
   `SKILL.md` 的 skill：
   - **新** skill 移进 `skills/`（成为唯一源码）；
   - **完全相同**的重复项备份后删除（以便改成软链）；
   - 同名但**内容不同**的是**冲突** —— 所有副本原样保留并报告，交给你决定。
2. **镜像** —— 把 `skills/` 里的每个 skill 软链进每个已安装、已纳管的 Agent。已存在
   的真实目录绝不覆盖（会报告为 *blocked*）。加 `--adopt-external` 时，软链到外部
   目录的 skill 会被复制进仓库并重定向。

## 配置

- **`config/registry.json`** —— 已知 Agent 目录及其各系统路径。新增 Agent 在这里加
  （用 `paths.default`，可选 `paths.windows` / `paths.macos` / `paths.linux`）。
- **`config/agents.json`** —— 你本机的选择：`enabled`（Agent 名列表，或 `"all"`）、
  `adopt_external`、`auto_commit`、`auto_push`，以及不在 registry 里的 `custom` Agent。
  由 `init` 生成。

只有当某 Agent 同时在 `enabled` 列表里**且**其配置目录在本机存在时才会被同步。

## 安全

- 默认 dry-run；真正改动需要 `--apply`。
- 绝不覆盖真实目录或有冲突的 skill。
- 删除的重复项备份到 `~/.skill-sync-backups/<时间戳>/`。
- 幂等 —— 一切已软链好时重复运行不做任何事。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
