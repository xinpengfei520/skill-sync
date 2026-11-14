#!/bin/sh
# skill-sync one-line installer (macOS / Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/xinpengfei520/skill-sync/main/install.sh | sh
#
# What it does:
#   1. reuses an existing checkout (./skill-sync, ~/skill-sync, ~/.skill-sync/tool)
#      or clones one to ~/.skill-sync/tool
#   2. writes a `skill-sync` launcher to ~/.local/bin
#   3. adds that directory to PATH in your shell rc (zsh / bash / profile)
#
# It never touches your skills library or config/agents.json. Re-running is safe.
#
# Environment overrides:
#   SKILL_SYNC_INSTALL_DIR=DIR   where the tool checkout lives (~/.skill-sync/tool)
#   SKILL_SYNC_BIN_DIR=DIR       where the launcher goes (~/.local/bin)
#   SKILL_SYNC_REPO=URL          git remote (public repo)
#   SKILL_SYNC_REF=REF           branch or tag (main)
#   SKILL_SYNC_NO_MODIFY_PATH=1  do not edit any shell rc
#   SKILL_SYNC_FORCE=1           back up and replace a foreign `skill-sync` file

set -eu

REPO_URL=${SKILL_SYNC_REPO:-https://github.com/xinpengfei520/skill-sync.git}
REF=${SKILL_SYNC_REF:-main}
BIN_DIR=${SKILL_SYNC_BIN_DIR:-$HOME/.local/bin}
DEFAULT_TOOL_DIR=$HOME/.skill-sync/tool
LEGACY_DIR=$HOME/skill-sync
MARK_BEGIN="# >>> skill-sync >>>"
MARK_END="# <<< skill-sync <<<"
LAUNCHER_MARK="# skill-sync launcher (generated)"

say() { printf '%s\n' "$*"; }
warn() { printf 'skill-sync: %s\n' "$*" >&2; }
die() { printf 'skill-sync: %s\n' "$*" >&2; exit 1; }

case ${1:-} in
  -h|--help)
    say "skill-sync installer"
    say ""
    say "  curl -fsSL https://raw.githubusercontent.com/xinpengfei520/skill-sync/main/install.sh | sh"
    say ""
    say "Environment:"
    say "  SKILL_SYNC_INSTALL_DIR=DIR   tool checkout (~/.skill-sync/tool)"
    say "  SKILL_SYNC_BIN_DIR=DIR       launcher dir (~/.local/bin)"
    say "  SKILL_SYNC_REPO=URL          git remote"
    say "  SKILL_SYNC_REF=REF           branch or tag (main)"
    say "  SKILL_SYNC_NO_MODIFY_PATH=1  do not edit any shell rc"
    say "  SKILL_SYNC_FORCE=1           replace a foreign \`skill-sync\` file"
    exit 0 ;;
esac

# --- dependencies -----------------------------------------------------------
command -v git >/dev/null 2>&1 || die "git is required but was not found"
command -v python3 >/dev/null 2>&1 || die "python3 is required but was not found"
PYTHON=$(command -v python3)
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "Python 3.9+ is required (found: $("$PYTHON" -V 2>&1))"

is_checkout() { [ -f "$1/bin/skill-sync.py" ] && [ -d "$1/skillsync" ]; }

# --- resolve the tool directory ---------------------------------------------
if [ -n "${SKILL_SYNC_INSTALL_DIR:-}" ]; then
  TOOL_DIR=$SKILL_SYNC_INSTALL_DIR
elif is_checkout "$DEFAULT_TOOL_DIR"; then
  TOOL_DIR=$DEFAULT_TOOL_DIR
elif is_checkout "$LEGACY_DIR"; then
  TOOL_DIR=$LEGACY_DIR
  say "Using the existing checkout at $TOOL_DIR"
else
  TOOL_DIR=$DEFAULT_TOOL_DIR
fi

# --- clone or update --------------------------------------------------------
if [ -d "$TOOL_DIR/.git" ] && is_checkout "$TOOL_DIR"; then
  if git -C "$TOOL_DIR" remote get-url origin >/dev/null 2>&1; then
    SRC=origin
  else
    SRC=$REPO_URL
  fi
  CUR=$(git -C "$TOOL_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  if git -C "$TOOL_DIR" fetch --quiet "$SRC" "$REF" < /dev/null 2>/dev/null; then
    if [ "$CUR" != "$REF" ]; then
      say "Leaving $TOOL_DIR on branch '$CUR'"
    elif git -C "$TOOL_DIR" merge --ff-only FETCH_HEAD < /dev/null > /dev/null 2>&1; then
      say "Updated $TOOL_DIR"
    else
      say "Keeping local commits in $TOOL_DIR (fast-forward not possible)"
    fi
  else
    warn "could not fetch updates; using the existing checkout"
  fi
elif [ -e "$TOOL_DIR" ]; then
  die "$TOOL_DIR exists but is not a skill-sync checkout; move it away or set SKILL_SYNC_INSTALL_DIR"
else
  say "Cloning into $TOOL_DIR"
  mkdir -p "$(dirname "$TOOL_DIR")"
  git clone --quiet --branch "$REF" "$REPO_URL" "$TOOL_DIR" < /dev/null \
    || die "git clone failed (check your network or set SKILL_SYNC_REPO)"
fi

is_checkout "$TOOL_DIR" || die "$TOOL_DIR does not look like a skill-sync checkout"

# --- bundled skill ----------------------------------------------------------
# Seed the library with the bundled skill-sync skill, but never overwrite a copy
# the user already has (it may be customized).
if [ -f "$HOME/.skill-sync/home" ]; then
  LIB_ROOT=$(cat "$HOME/.skill-sync/home" 2>/dev/null || true)
  LIB_DIR=${LIB_ROOT:-$HOME/.skill-sync}/skills
elif [ -f "$TOOL_DIR/config/agents.json" ]; then
  LIB_DIR=$TOOL_DIR/skills        # legacy combined checkout
else
  LIB_DIR=$HOME/.skill-sync/skills
fi
if [ -d "$TOOL_DIR/skills/skill-sync" ]; then
  if [ ! -e "$LIB_DIR/skill-sync" ] && [ ! -L "$LIB_DIR/skill-sync" ]; then
    mkdir -p "$LIB_DIR"
    cp -R "$TOOL_DIR/skills/skill-sync" "$LIB_DIR/skill-sync"
    say "Installed the bundled skill-sync skill into $LIB_DIR"
  elif [ -d "$LIB_DIR/skill-sync" ] && [ ! -L "$LIB_DIR/skill-sync" ] \
       && ! cmp -s "$TOOL_DIR/skills/skill-sync/SKILL.md" \
                 "$LIB_DIR/skill-sync/SKILL.md"; then
    BK="$HOME/.skill-sync/backups/bundled-skill-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BK"
    mv "$LIB_DIR/skill-sync" "$BK/skill-sync"
    cp -R "$TOOL_DIR/skills/skill-sync" "$LIB_DIR/skill-sync"
    say "Refreshed the bundled skill-sync skill (previous copy: $BK)"
  fi
fi

# --- launcher ---------------------------------------------------------------
LAUNCHER=$BIN_DIR/skill-sync
mkdir -p "$BIN_DIR"
if [ -e "$LAUNCHER" ] && ! grep -qF "$LAUNCHER_MARK" "$LAUNCHER" 2>/dev/null; then
  if [ "${SKILL_SYNC_FORCE:-0}" = "1" ]; then
    BACKUP=$LAUNCHER.bak-$(date +%Y%m%d%H%M%S)
    mv "$LAUNCHER" "$BACKUP"
    say "Backed up the existing launcher to $BACKUP"
  else
    die "$LAUNCHER already exists and was not created by this installer; set SKILL_SYNC_FORCE=1 to back it up and replace it"
  fi
fi
cat > "$LAUNCHER" <<EOF
#!/bin/sh
$LAUNCHER_MARK
# Do not edit: re-run install.sh to regenerate this file.
if [ -x "$PYTHON" ]; then PY="$PYTHON"; else PY=python3; fi
exec "\$PY" "$TOOL_DIR/bin/skill-sync.py" "\$@"
EOF
chmod +x "$LAUNCHER"
say "Installed launcher: $LAUNCHER"

# --- PATH -------------------------------------------------------------------
if [ "${SKILL_SYNC_NO_MODIFY_PATH:-0}" = "1" ]; then
  say "Skipped shell PATH setup (SKILL_SYNC_NO_MODIFY_PATH=1)"
else
  RC=
  case "$(basename "${SHELL:-}")" in
    zsh) RC=$HOME/.zshrc ;;
    bash)
      if [ -f "$HOME/.bashrc" ]; then RC=$HOME/.bashrc
      elif [ -f "$HOME/.bash_profile" ]; then RC=$HOME/.bash_profile
      else RC=$HOME/.bashrc; fi ;;
    *) [ -f "$HOME/.profile" ] && RC=$HOME/.profile ;;
  esac

  if [ -z "$RC" ]; then
    warn "could not detect your shell rc; add this line yourself:"
    warn "  export PATH=\"$BIN_DIR:\$PATH\""
  elif grep -qF "$MARK_BEGIN" "$RC" 2>/dev/null; then
    say "PATH already configured in $RC"
  else
    touch "$RC"
    {
      printf '\n%s\n' "$MARK_BEGIN"
      # shellcheck disable=SC2016  # $PATH must stay literal in the rc file
      printf 'case ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n' \
        "$BIN_DIR" "$BIN_DIR"
      printf '%s\n' "$MARK_END"
    } >> "$RC"
    say "Added $BIN_DIR to PATH in $RC"
  fi
fi

# --- report -----------------------------------------------------------------
VERSION=$("$LAUNCHER" --version < /dev/null 2>/dev/null || echo "skill-sync")
say ""
say "skill-sync is installed."
say "  tool:     $TOOL_DIR"
say "  launcher: $LAUNCHER"
say "  version:  $VERSION"
if [ -f "$HOME/.skill-sync/home" ]; then
  say "  library:  $(cat "$HOME/.skill-sync/home" 2>/dev/null) (existing config kept)"
else
  say "  library:  $HOME/.skill-sync/skills (default; set SKILL_SYNC_HOME to split)"
fi
if [ -n "${RC:-}" ] && ! printf '%s' ":$PATH:" | grep -qF ":$BIN_DIR:"; then
  say ""
  say "Open a new shell, or run:  . \"$RC\""
fi
say ""
say "Next:  skill-sync migrate --apply   # consolidate an existing library"
say "       skill-sync init"
