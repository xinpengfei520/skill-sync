<p align="center">
  <img src="https://image.vance.xin/skill-sync/20261114-skill-sync-architecture-2.webp" alt="skill-sync — すべての Agent の skills を 1 つのリポジトリに集約し、ミラーする" width="100%">
</p>

# skill-sync

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/version-0.4.1-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs welcome">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <b>日本語</b> ·
  <a href="README.ko.md">한국어</a>
</p>

**ローカルのすべての AI エージェントが使う Skills を、Git で一元管理する唯一の情報源。**

最近の AI エージェント —— Claude Code、Codex、Cursor、Gemini CLI、Copilot、Windsurf、
WorkBuddy など —— はいずれも [Skills](https://www.anthropic.com/news/skills)
（`SKILL.md` フォルダ）に対応していますが、保存場所はそれぞれ異なります。あるエージェント
にインストールしても他にはなく、片方で編集するとコピーがずれていきます。

`skill-sync` はこれを解決します。各スキルの正本を [`skills/`](skills/) にまとめ、
インストール済みのすべてのエージェントを**シンボリックリンク**でそこへ向けます。
ここで一度編集すればすべてのエージェントに反映され、1 つのエージェントにだけ入れた
スキルも次回の同期で他へ共有されます。

```
             ┌─────────────────────────────┐
             │   skills/  (このリポジトリ, Git)  │   ← 唯一の情報源
             └──────────────┬──────────────┘
        ┌───────────┬───────┼───────┬───────────┐
      リンク       リンク    リンク   リンク       リンク
        ▼           ▼        ▼       ▼           ▼
   ~/.claude/   ~/.codex/  ~/.cursor/ ~/.gemini/  … すべてのインストール済みエージェント
```

## 特徴

- **収集 + 全ミラー** —— 各エージェントからソースでインストールされたスキルをリポジトリ
  に集め、すべてのスキルを各エージェントへリンクし直して常に一致させます。
- **インストール済みのみ操作** —— 端末に存在するエージェントを自動検出し、未インストール
  のエージェントにはフォルダを作りません。
- **初回選択** —— `init` で管理するエージェントを選べます（または全部）。
- **自動同期** —— `schedule --interval 1h` で OS ネイティブのタイマーを登録、または
  フォアグラウンドの `watch` ループ。スケジュールに従って同期し、任意で自動 commit/push。
- **クロスプラットフォーム** —— macOS / Linux / Windows 対応（Windows では実シンボリック
  リンクが使えない場合ディレクトリジャンクションにフォールバック）。
- **安全** —— 既定はドライラン。実ディレクトリを上書きせず、内容の競合は報告のみで自動
  解決しません。削除した重複はバックアップ。冪等。

## インストール

### 方法 A —— ワンライン（macOS / Linux）

```bash
curl -fsSL https://raw.githubusercontent.com/xinpengfei520/skill-sync/main/install.sh | sh
```

ツールを `~/.skill-sync/tool` にクローンし（既存の checkout、たとえば
`~/skill-sync` があればそれを再利用）、`~/.local/bin` に `skill-sync`
ランチャーを作成して PATH に追加します（`~/.zshrc` または `~/.bashrc`）。
`git` と Python 3.9+ が必要です。再実行すると checkout を更新しますが、
skills ライブラリや `config/agents.json` には触れません。初回インストール時に
ツール同梱の `skill-sync` スキルをライブラリへコピーし、内容が異なる場合は
ツール版で更新します（旧コピーは `backups/` に保存）。

その後：

```bash
skill-sync init
```

### 方法 B —— AI エージェントで一発インストール（貼るだけ）

以下をコピーして任意の AI エージェント（Claude Code、Codex、Cursor…）に貼り付けると、
リポジトリのクローン・エージェント検出・同期まで実行します：

```text
「skill-sync」をインストールして —— ローカルのすべての AI エージェントの Skills を 1 つの Git リポジトリで同期するツールです。

1. ~/skill-sync が無ければ実行：
   git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
2. 同期をプレビュー（インストール済みのエージェントを検出、何も変更しない）：
   python3 ~/skill-sync/bin/skill-sync.py init --all
3. 計画を見せて。競合が無ければ適用：
   python3 ~/skill-sync/bin/skill-sync.py --apply
4. どのエージェントを検出し、いくつのスキルが共有されたか教えて。

Python 3.9+ が必要。既存のスキルを上書きしないで —— 同名でも内容が異なる場合は止めて確認して。
```

> **ヒント：** 一度インストールすれば、あとは任意のエージェントに *「スキルを同期して」*
> と言うだけで再同期できます —— `skill-sync` スキルは各エージェントにミラーされている
> ので、コマンドを覚える必要はありません。

### 方法 C —— 手動

依存は **Python 3.9+** のみ。クローンして実行するだけ：

```bash
git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
cd ~/skill-sync
python3 bin/skill-sync.py --version
```

必要なら `skill-sync` コマンドを導入（`pip install -e .`）。スキルのリポジトリを別の場所
に置く場合は `export SKILL_SYNC_HOME=~/my-skills` で指定します。

## クイックスタート

```bash
# 1. 管理するインストール済みエージェントを選ぶ（対話式、または --all）
skill-sync init

# 2. 同期内容をプレビュー（何も変更されない）
skill-sync

# 3. 実行
skill-sync --apply

# 4. コミットして push（このリポジトリが唯一の情報源）
git add -A && git commit -m "sync skills" && git push
```

インストーラーではなく手動 `git clone` の場合は、`skill-sync` を
`python3 bin/skill-sync.py` に読み替えてください。

## コマンド

| コマンド | 説明 |
|---|---|
| `init [--all\|--agents a,b]` | エージェントを検出し、管理対象を選び、設定を保存して同期 |
| `sync [--apply]` | 収集 + ミラー。`--apply` なしはドライラン |
| `uninstall <skill> … [--apply]` | ライブラリと全エージェントからスキルを削除。`--apply` なしはドライラン |
| `agent add <name> [--path DIR]` | 単一エージェントの同期を開始（skills ディレクトリを自動解決。`--apply` なしはプレビューのみ） |
| `agent remove <name> [--prune-links]` | 単一エージェントの同期を停止。任意でライブラリを指すリンクを回収 |
| `status` | プラットフォーム、エージェント一覧、自動同期の状態、ドライラン概要 |
| `list` | 既知のすべてのエージェントとその状態を表示 |
| `doctor [--agent NAME] [--json] [--strict]` | 読み取り専用のヘルスチェック：スキル数、サイズ、frontmatter の妥当性、最適化の提案 |
| `migrate [--apply]` | 旧レイアウトを `~/.skill-sync` に移行（`--apply` なしはドライラン） |
| `watch --interval 10m` | フォアグラウンドで一定間隔ごとに同期 |
| `schedule --interval 1h` | OS ネイティブのタイマーを登録（launchd / タスク スケジューラ / systemd） |
| `unschedule` | タイマーを削除 |
| `update [--check]` | ツールを最新版に更新（git pull） |
| `backup [--set URL]` | スキルを自分の Git リポジトリにバックアップ（既定はオフ） |

よく使う `sync` オプション：`--adopt-external`（外部ハブへリンクされたスキルを取り込む）、
`--agent NAME`（対象を限定）、`--commit --push`（適用後に git）、`--json`、`--no-backup`。

### エージェントの追加 / 削除

```bash
# registry にある既知のエージェントを同期
python3 bin/skill-sync.py agent add cursor

# registry にないエージェント：skills ディレクトリを明示
python3 bin/skill-sync.py agent add dsh --path ~/.dsh/skills --display "DeepSeek Harness"

# 同期を停止し、ライブラリを指すリンクを回収
python3 bin/skill-sync.py agent remove dsh --prune-links --apply
```

`agent add` は skills ディレクトリを次の順で解決します：registry
（`config/registry.json`）→ `custom` エントリ（`config/agents.json`）→ `--path` →
規約パスの探索（`~/.<name>/skills`、`~/.config/<name>/skills`）。探索は実際に存在する
パスのみを採用し、既に別のエージェントが使っているディレクトリを別名で登録することは
拒否します（同じディレクトリを二重に同期してしまうため）。`agent add` は既定で同期を
プレビューし、`--apply` で実行します。

`agent remove` は選択だけを変更します。既存のリンクは `--prune-links` を付けるまで
残ります（既定はドライラン、`--apply` で削除）。ライブラリを指すリンクのみを回収し、
実ディレクトリや外部ハブへのリンクは報告したうえでそのまま残します。

### ディレクトリ構成

```
~/.skill-sync/
├── skills/     スキルライブラリ（スキルごとに 1 ディレクトリ）
├── config/     agents.json（管理対象のエージェント）
├── backups/    削除・重複解消前のバックアップ
├── logs/       定期実行の autosync.log
└── tool/       ツール本体（ワンラインインストール時）
```

`skills/`、`config/` など追跡対象のファイルが git リポジトリを構成し、
`backups/`、`logs/`、`tool/`、`home` は `.gitignore` で除外されます。既定では
ローカルにコミットするだけです。リモート（`origin` または
`skill-sync backup --set`）があれば push し、git がなければコミットせず
ファイルをローカルで同期します。

`skill-sync migrate` は旧レイアウト（`~/my-skills`、`~/.skill-sync-backups`、
`~/.skill-sync/autosync.log`）を新構成へ移し、エージェントのシンボリック
リンクを付け替え、自動同期ジョブを書き換えます。既定はドライランで、
`--apply` で実行します。安全な移行は次のコマンド実行時にも自動で行われます。

### ヘルスチェック

```bash
python3 bin/skill-sync.py doctor          # 人間が読むレポート
python3 bin/skill-sync.py doctor --json   # 機械可読
python3 bin/skill-sync.py doctor --strict # error があれば終了コード 1
```

`--limit N` はサイズ表の行数（`--all` で全スキルと全 info を表示）、
`--agent NAME` は対象エージェントを絞り込みます。

`doctor` は完全に読み取り専用です。インストール済みスキルの数、各スキルの
サイズ、name + description がコンテキストに占める量、各エージェントの同期
ずれ（欠落リンク、ダングリングリンク、ミラーを妨げる実ディレクトリ）を報告
します。チェック項目は Agent Skills 仕様に沿っています：

- `name` と `description` を含む解析可能な frontmatter
- `name` は kebab-case で 64 文字以内
- `description` は 1024 文字以内で、`<` や `>` を含まない
- `SKILL.md` は 500 行以内（詳細は `references/` へ）

### 自動同期

```bash
# 1 時間ごとにバックグラウンド同期、自動 commit+push、再起動後も有効
python3 bin/skill-sync.py schedule --interval 1h

# もしくはフォアグラウンドの簡易ループ
python3 bin/skill-sync.py watch --interval 10m
```

間隔は `s`/`m`/`h`/`d` を受け付けます（例：`90s`、`10m`、`1h`、`12h`、`24h`、`1d`）。
数字のみは分。最小 `30s`。ログは `~/.skill-sync/autosync.log`。

### 更新とバックアップ

```bash
# skill-sync を最新版に更新
python3 bin/skill-sync.py update            # または：update --check

# スケジュール実行のたびに自己更新
python3 bin/skill-sync.py schedule --interval 1h --auto-update

# スキルを自分の Git リポジトリにバックアップ（既定はオフ）
python3 bin/skill-sync.py backup --set git@github.com:you/my-skills-backup.git
python3 bin/skill-sync.py backup            # 手動で push；スケジュール同期後にも自動 push
```

`update` は fast-forward、またはローカルのスキルコミットの上に rebase します。`backup`
は自分が管理する 2 つ目の Git リモートへ push します —— 上流からクローンしつつ自分の
スキルを別に保管したいときに便利です。

## 同期の仕組み

1. **収集** —— 各エージェントの skills ディレクトリから、`SKILL.md` を含む**実ディレクトリ**
   （シンボリックリンクは無視）を探します：
   - **新規**スキルは `skills/` へ移動（正本になる）、
   - **同一**の重複はバックアップして削除（リンクに置き換えるため）、
   - 同名で**内容が異なる**ものは**競合** —— すべてのコピーをそのまま残して報告します。
2. **ミラー** —— `skills/` の各スキルを、インストール済みで管理対象の各エージェントへ
   リンクします。既存の実ディレクトリは決して上書きしません（*blocked* として報告）。
   `--adopt-external` を付けると、外部ハブへリンクされたスキルをリポジトリへコピーして
   リンクし直します。

## 設定

- **`config/registry.json`** —— 既知エージェントと OS ごとのスキルパスのカタログ。新しい
  エージェントはここに追加します（`paths.default` と任意の `paths.windows` /
  `paths.macos` / `paths.linux`）。
- **`config/agents.json`** —— この端末の選択：`enabled`（エージェント名のリスト、または
  `"all"`）、`disabled`（`enabled` が `"all"` でも除外するエージェント）、
  `adopt_external`、`auto_commit`、`auto_push`、registry にない `custom`
  エージェント。`init` と `agent add/remove` が書き込みます。

エージェントは有効で、`disabled` に含まれず、**かつ**設定ディレクトリが端末に存在する
場合のみ同期されます。

## 安全性

- 既定はドライラン。実際の変更には `--apply` が必要。
- 実ディレクトリや競合スキルを決して上書きしません。
- 削除した重複は `~/.skill-sync-backups/<タイムスタンプ>/` にバックアップ。
- 冪等 —— すべてリンク済みなら再実行しても何も起きません。

## ライセンス

MIT —— [LICENSE](LICENSE) を参照。
