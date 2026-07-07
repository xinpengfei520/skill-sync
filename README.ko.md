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
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <b>한국어</b>
</p>

**로컬의 모든 AI 에이전트가 사용하는 Skills를 Git으로 관리하는 단일 원본 소스.**

요즘 AI 에이전트 —— Claude Code, Codex, Cursor, Gemini CLI, Copilot, Windsurf,
WorkBuddy 등 —— 은 모두 [Skills](https://www.anthropic.com/news/skills)
(`SKILL.md` 폴더)를 지원하지만, 저장 위치가 저마다 다릅니다. 한 에이전트에 설치하면
다른 에이전트에는 없고, 한쪽에서 수정하면 사본들이 어긋납니다.

`skill-sync`가 이를 해결합니다. 모든 스킬의 정본을 [`skills/`](skills/) 아래에 모아 두고,
설치된 모든 에이전트가 **심볼릭 링크**로 그곳을 가리키게 합니다. 여기서 한 번 수정하면
모든 에이전트에 반영되고, 한 에이전트에만 설치한 스킬도 다음 동기화 때 나머지에 공유됩니다.

```
             ┌─────────────────────────────┐
             │   skills/  (이 저장소, Git 관리)  │   ← 단일 원본 소스
             └──────────────┬──────────────┘
        ┌───────────┬───────┼───────┬───────────┐
       링크        링크      링크    링크         링크
        ▼           ▼        ▼       ▼           ▼
   ~/.claude/   ~/.codex/  ~/.cursor/ ~/.gemini/  … 설치된 모든 에이전트
```

## 특징

- **수집 + 전체 미러링** —— 각 에이전트에서 소스로 설치된 스킬을 저장소로 모은 뒤,
  모든 스킬을 각 에이전트로 다시 링크해 항상 동일하게 유지합니다.
- **설치된 것만 처리** —— 기기에 존재하는 에이전트를 자동 감지하며, 설치되지 않은
  에이전트용 폴더는 만들지 않습니다.
- **최초 선택** —— `init`으로 관리할 에이전트를 고를 수 있습니다(또는 전체).
- **자동 동기화** —— `schedule --interval 1h`로 OS 기본 타이머를 등록하거나 포그라운드
  `watch` 루프 실행. 일정에 따라 동기화하며 선택적으로 자동 commit/push.
- **크로스 플랫폼** —— macOS / Linux / Windows 지원(Windows에서 실제 심볼릭 링크가
  허용되지 않으면 디렉터리 정션으로 대체).
- **안전** —— 기본은 드라이런. 실제 디렉터리를 덮어쓰지 않고, 내용 충돌은 보고만 하며
  자동 해결하지 않습니다. 삭제한 중복은 백업. 멱등.

## 설치

### 방법 A —— AI 에이전트로 원클릭 설치(붙여넣기만)

아래를 복사해 아무 AI 에이전트(Claude Code, Codex, Cursor…)에 붙여넣으면 저장소 클론·
에이전트 감지·동기화까지 실행합니다:

```text
"skill-sync"를 설치해줘 —— 로컬의 모든 AI 에이전트 Skills를 하나의 Git 저장소로 동기화하는 도구야.

1. ~/skill-sync가 없으면 실행:
   git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
2. 동기화 미리보기(설치된 에이전트 감지, 아무것도 변경 안 함):
   python3 ~/skill-sync/bin/skill-sync.py init --all
3. 계획을 보여줘. 충돌이 없으면 적용:
   python3 ~/skill-sync/bin/skill-sync.py --apply
4. 어떤 에이전트가 감지됐고 몇 개의 스킬이 공유됐는지 알려줘.

Python 3.9+ 필요. 기존 스킬을 덮어쓰지 마 —— 같은 이름인데 내용이 다르면 멈추고 확인해줘.
```

> **팁:** 한 번 설치하면 이후에는 아무 에이전트에게 *"내 스킬 동기화해줘"* 라고만 하면
> 다시 동기화됩니다 —— `skill-sync` 스킬이 모든 에이전트에 미러링되어 있어 명령을 외울
> 필요가 없습니다.

### 방법 B —— 수동

**Python 3.9+** 외에 의존성이 없습니다. 클론 후 바로 실행:

```bash
git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
cd ~/skill-sync
python3 bin/skill-sync.py --version
```

원하면 `skill-sync` 명령을 설치하세요(`pip install -e .`). 설치 후 스킬 저장소가 다른
곳에 있다면 `export SKILL_SYNC_HOME=~/my-skills`로 지정합니다.

## 빠른 시작

```bash
# 1. 관리할 설치된 에이전트 선택(대화형 또는 --all)
python3 bin/skill-sync.py init

# 2. 동기화 미리보기(아무것도 바뀌지 않음)
python3 bin/skill-sync.py

# 3. 적용
python3 bin/skill-sync.py --apply

# 4. 커밋 & 푸시(이 저장소가 단일 원본 소스)
git add -A && git commit -m "sync skills" && git push
```

## 명령어

| 명령 | 설명 |
|---|---|
| `init [--all\|--agents a,b]` | 설치된 에이전트 감지, 관리 대상 선택, 설정 저장 후 동기화 |
| `sync [--apply]` | 수집 + 미러링. `--apply` 없으면 드라이런 |
| `status` | 플랫폼, 에이전트 표, 자동 동기화 상태, 드라이런 요약 |
| `list` | 알려진 모든 에이전트와 설치/관리 상태 표시 |
| `watch --interval 10m` | 포그라운드에서 일정 간격마다 동기화 |
| `schedule --interval 1h` | OS 기본 타이머 등록(launchd / 작업 스케줄러 / systemd) |
| `unschedule` | 타이머 제거 |
| `update [--check]` | 도구를 최신 버전으로 업데이트(git pull) |
| `backup [--set URL]` | 스킬을 내 Git 저장소에 백업(기본은 꺼짐) |

자주 쓰는 `sync` 옵션: `--adopt-external`(외부 허브로 링크된 스킬을 편입),
`--agent NAME`(특정 에이전트로 한정), `--commit --push`(적용 후 git), `--json`,
`--no-backup`.

### 자동 동기화

```bash
# 1시간마다 백그라운드 동기화, 자동 commit+push, 재부팅 후에도 유지
python3 bin/skill-sync.py schedule --interval 1h

# 또는 간단한 포그라운드 루프
python3 bin/skill-sync.py watch --interval 10m
```

간격은 `s`/`m`/`h`/`d`를 지원합니다(예: `90s`, `10m`, `1h`, `12h`, `24h`, `1d`).
숫자만 쓰면 분 단위. 최소 `30s`. 로그는 `~/.skill-sync/autosync.log`.

### 업데이트 & 백업

```bash
# skill-sync를 최신 버전으로 업데이트
python3 bin/skill-sync.py update            # 또는: update --check

# 예약 실행마다 자체 업데이트
python3 bin/skill-sync.py schedule --interval 1h --auto-update

# 스킬을 내 Git 저장소에 백업(기본은 꺼짐)
python3 bin/skill-sync.py backup --set git@github.com:you/my-skills-backup.git
python3 bin/skill-sync.py backup            # 수동 푸시; 예약 동기화 후에도 자동 푸시
```

`update`는 fast-forward 하거나 로컬 스킬 커밋 위에 rebase 합니다. `backup`은 당신이
관리하는 두 번째 Git 원격으로 푸시합니다 —— 업스트림에서 클론하면서 자신의 스킬을
따로 보관하고 싶을 때 유용합니다.

## 동기화 원리

1. **수집** —— 각 에이전트의 skills 디렉터리에서 `SKILL.md`가 있는 **실제 디렉터리**
   (심볼릭 링크는 무시)를 찾습니다:
   - **새** 스킬은 `skills/`로 이동(정본이 됨),
   - **동일한** 중복은 백업 후 삭제(링크로 교체하기 위해),
   - 이름은 같지만 **내용이 다른** 것은 **충돌** —— 모든 사본을 그대로 두고 보고합니다.
2. **미러링** —— `skills/`의 모든 스킬을 설치되고 관리 대상인 각 에이전트로 링크합니다.
   기존 실제 디렉터리는 절대 덮어쓰지 않습니다(*blocked*로 보고). `--adopt-external`을
   붙이면 외부 허브로 링크된 스킬을 저장소로 복사하고 다시 링크합니다.

## 설정

- **`config/registry.json`** —— 알려진 에이전트와 OS별 스킬 경로 카탈로그. 새 에이전트는
  여기에 추가합니다(`paths.default` 및 선택적 `paths.windows` / `paths.macos` /
  `paths.linux`).
- **`config/agents.json`** —— 이 기기의 선택: `enabled`(에이전트 이름 목록 또는 `"all"`),
  `adopt_external`, `auto_commit`, `auto_push`, 그리고 registry에 없는 `custom`
  에이전트. `init`이 생성합니다.

에이전트는 `enabled`에 있고 **동시에** 설정 디렉터리가 기기에 존재할 때만 동기화됩니다.

## 안전

- 기본은 드라이런. 실제 변경에는 `--apply`가 필요합니다.
- 실제 디렉터리나 충돌 스킬을 절대 덮어쓰지 않습니다.
- 삭제한 중복은 `~/.skill-sync-backups/<타임스탬프>/`에 백업됩니다.
- 멱등 —— 모두 링크된 상태에서 다시 실행해도 아무 일도 하지 않습니다.

## 라이선스

MIT —— [LICENSE](LICENSE) 참조.
