Status: proposed, for the owner's approval.

## Why

A request that matches an instant command skips Claude. Today the only instant commands are the hard-coded ones in
`quick.handle` (`app/quick.py:350-428`). "Pause the music" always runs `_media("pause")` (`app/quick.py:383-384`,
`app/quick.py:103`), which on macOS drives Spotify or Music (`app/macsys.py:197-214`). On this Mac the music plays
through Roon, so the built-in pauses nothing. There is no way to point a built-in at another command (`roonctl`), and no
way to add a phrase that runs a command of the owner's choosing.

The pieces share these concerns. Each already has copies in the tree:

- **Running a helper program and reading its output**: 4 copies. `quick._run` (`app/quick.py:39`), `macsys._run`
  (`app/macsys.py:22`), `server._run` (`app/server.py:799`, bytes, used by `capture`) and `winsys.ps`
  (`app/winsys.py:22`, PowerShell).
- **Starting a detached helper**: 3 copies. `app/quick.py:301`, `app/quick.py:311` and `app/macsys.py:266`.
- **A child in its own process group**: 2 copies. `server.spawn_kw` (`app/server.py:1345`) and `agents.own_group_kw`
  (`app/agents.py:326`).
- **Stopping a process group**: 3 copies. `server.kill` (`app/server.py:1350`), `agents.kill_tree`
  (`app/agents.py:299`) and the inline killpg/taskkill in `stop_proc` (`app/server.py:3170-3177`).
- **A UTF-8 locale for a child**: 2 copies. `app/macsys.py:26` and `app/server.py:2984-2987`.
- **Reading a spoken request before matching it** (case, curly quotes, the wake word, "please"/"can you", the 120-char
  cap): 2 Python copies, `app/quick.py:351-355` and `app/recall.py:158-161`. The page's own patterns repeat the
  wake-word prefix as well: `app/static/index.html:2053-2054` and `app/static/index.html:2124-2128`.
- **Dispatch of instant commands**: split over two places. The page answers memory, live-view and tidy phrases itself
  (`app/static/index.html:2134-2144`) and then posts `/api/quick` (`app/static/index.html:2146-2147`). The server tries
  `recall.answer` (`app/server.py:3920`) and then `quick.handle` (`app/server.py:3923`).
- **Config**: one default table, `DEFAULTS` (`app/server.py:116`), loaded once at start (`app/server.py:258`) and
  written by `save_config` (`app/server.py:2781`). `/api/settings` validates each key inline (`app/server.py:3837-3915`).
  `quick_actions` (`app/server.py:222`, validated at `app/server.py:3896-3902`) is a different feature: one-tap prompts
  to Claude on the menu.
- **Test config injection**: `tests/test_quick_projects.py:17-26` swaps `quick.cfg` / `quick.save_config` for a dict.

## Modules

`app/procs.py` (new): the one place Void starts, runs and stops a child process.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Ran:
    ok: bool              # started, and exited 0 within the timeout
    out: str              # stdout, stripped
    err: str              # last 400 chars of stderr, or why it never ran, or "timed out after 10s"
    code: int | None      # exit code; None when it never started or was killed at the timeout

def utf8_env(base: dict | None = None) -> dict: ...
    # base (default os.environ) plus LANG=en_US.UTF-8 when no UTF-8 locale is set (LC_ALL / LC_CTYPE dropped then)
def own_group_kw() -> dict: ...
    # Popen kwargs: the child in its own process group (Windows: its own console group, no window)
def kill_tree(p, grace: float = 1.5) -> None: ...
    # stop p and its whole group: SIGTERM, wait grace, SIGKILL, wait grace (Windows: taskkill /T /F)
def stop_group(p) -> None: ...
    # SIGTERM to p's group, no wait (Windows: taskkill /T /F); nothing when p is gone
def run(argv: list[str], timeout: float = 10, env: dict | None = None, cwd: str | None = None) -> Ran: ...
    # own process group, env defaults to utf8_env(), output decoded UTF-8 with errors replaced;
    # at the timeout the whole group is killed with kill_tree
def spawn(argv: list[str], env: dict | None = None, cwd: str | None = None): ...
    # -> subprocess.Popen | None: detached (own group, stdio to DEVNULL), not waited on; None when it can't start
def shell_argv(line: str) -> list[str]: ...
    # the argv that runs a command line: ["/bin/sh", "-c", line];
    # Windows: ["powershell", "-NoProfile", "-NonInteractive", "-Command", line]
def quote(value: str) -> str: ...
    # value as one word of the shell shell_argv runs: shlex.quote on POSIX; on Windows a PowerShell
    # single-quoted string, each ' doubled
```

Replaces `quick._run` (`app/quick.py:39`), `macsys._run` (`app/macsys.py:22`), the detached Popens at
`app/quick.py:301`, `app/quick.py:311` and `app/macsys.py:266`, `server.spawn_kw` (`app/server.py:1345`),
`server.kill` (`app/server.py:1350`), the inline group stop in `stop_proc` (`app/server.py:3170-3177`),
`agents.kill_tree` (`app/agents.py:299`) and `agents.own_group_kw` (`app/agents.py:326`). `agents.Brain` keeps its
`killer=` parameter, now defaulting to `procs.kill_tree` (`app/agents.py:349`). `macsys.osa` and the other `macsys`
callers read `Ran.ok` / `Ran.out`.

`app/spoken.py` (new): how a spoken or typed request is read before anything matches it. Pure. It has no imports from
`app/`.

```python
def normalize(text: str) -> str: ...
    # lower case, curly quote to ', whitespace collapsed, " .!?" stripped at both ends, then one leading
    # "hey void" / "void" / "ok void" / "okay void" (with its comma or space), one leading
    # "please" / "can you" / "could you" / "would you" / "will you", one trailing "please";
    # "" when the result is over 120 characters
```

Replaces `app/quick.py:351-355` and `app/recall.py:158-161`.

`app/quick.py` (changed): the built-in instant actions, each under a stable name. The matcher and the action are
split, so a match can be handed to a user command instead of the built-in.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Intent:
    name: str             # a key of INTENTS
    args: dict            # what the matcher read from the words; every field INTENTS lists is filled

INTENTS: dict[str, tuple[str, ...]] = {          # name -> the args its matcher fills
    "project.switch": ("name", "path"),
    "volume.set": ("n",), "volume.up": ("n",), "volume.down": ("n",),   # up/down: n defaults to 10
    "volume.mute": (), "volume.unmute": (), "volume.get": (),
    "media.pause": (), "media.play": (), "media.next": (), "media.previous": (), "media.what": (),
    "bright.set": ("n",), "bright.up": (), "bright.down": (),
    "timer.set": ("secs", "what"), "timer.left": (), "timer.cancel": (),
    "time": (), "date": (), "lock": (), "app.open": ("app",),
}

def match(t: str) -> Intent | None: ...
    # t is spoken.normalize()d. The matchers of app/quick.py:358-427, in the same order, with no side effects.
    # A matcher that can't read its args lets the next one try, as handle does now (app/quick.py:361-363, 409-412)
def act(intent: Intent) -> dict | None: ...
    # the built-in action -> reply {"say", "mood", "sfx"?, "cd"?} (app/quick.py:3-4), or None (goes to Claude)
```

`quick.handle` is removed; `commands.handle` replaces it. `projects`, `add_project`, `_find_project`, the timers and
the wiring globals (`app/quick.py:28-31`) stay.

`app/commands.py` (new): the owner's own voice commands, and the one dispatch of every instant command.

```python
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Command:
    name: str                       # shown in Settings, in the failure reply and in the log line
    say: tuple[str, ...]            # exact phrases, spoken.normalize()d at load
    match: tuple[re.Pattern, ...]   # regular expressions, compiled at load, each full-matched against the
                                    # normalize()d request; their named groups fill {field}s
    replaces: str                   # a quick.INTENTS name, or ""
    run: str                        # a command line, run by the shell procs.shell_argv names; each "{field}" is
                                    # filled with procs.quote(value), so a value from speech is one word
    reply: str                      # said on success; "{out}" is the command's stdout, first 300 chars; default "Done."
    wait: bool                      # True (default): run to the end and report; False: procs.spawn and reply at once
    timeout: float                  # seconds when wait, default 10, clamped to 1-60

def load(cfg: dict) -> tuple[list[Command], list[str]]: ...
    # cfg["voice_commands"] -> (the commands, one "why" per entry skipped). A command may carry any of say, match
    # and replaces at once. An entry is skipped when: run is not a non-empty string; it has none of say, match
    # and replaces; a pattern does not compile; replaces is not in quick.INTENTS; a {field} is not filled on every
    # route the entry has (an exact phrase fills none; each pattern must name it as a group; replaces must list
    # it among its INTENTS fields); a phrase, a pattern or a replaces is already taken by an earlier entry
def find(t: str, cmds: list[Command]) -> tuple[Command, dict] | None: ...
    # t is spoken.normalize()d. First a command one of whose phrases equals t, with {}; else the first
    # command, in entry order, one of whose patterns full-matches t, with that match's named groups
def override(intent: "quick.Intent", cmds: list[Command]) -> Command | None: ...
def run(cmd: Command, args: dict | None = None) -> dict: ...
    # fields filled; procs.run(procs.shell_argv(line), cmd.timeout) or procs.spawn(procs.shell_argv(line)).
    # -> {"say", "mood", "sfx"?}: success says cmd.reply; failure (a non-zero exit, a timeout, or a spawn that
    # can't start) says "<name> didn't work" plus the first line of Ran.err. One stderr line per run:
    # "[void] command <name>: <ok | exit n | timed out | can't start>: <err tail>"
def handle(text: str, cfg: dict) -> dict | None: ...
    # t = spoken.normalize(text); "" -> None. Then, in order: find(t) -> run(cmd, groups);
    # recall.answer(text) -> {"say": answer, "mood": "happy"}; quick.match(t) -> run(override, intent.args)
    # if override else quick.act. The first that answers ends the dispatch: an owner's command, override or
    # not, answers with run's reply whether it worked or failed, and nothing after it is tried
```

`app/server.py` (changed): wiring only.

```python
DEFAULTS["voice_commands"] = []   # a list of command entries (below)
# /api/quick: r = commands.handle(said, CFG); the "cd" handling of app/server.py:3924-3929 stays
# state_info(): "voice_commands": CFG["voice_commands"], "voice_command_errors": commands.load(CFG)[1]
# /api/settings: "voice_commands" in the body is stored only as the entries commands.load accepts
```

A config entry, as the owner writes it in `config.json` or the Settings editor saves it:

```json
"voice_commands": [
  {"name": "Roon pause", "replaces": "media.pause", "run": "roonctl pause", "reply": "Paused."},
  {"name": "Roon what", "replaces": "media.what", "run": "roonctl now-playing | head -1", "reply": "That's {out}."},
  {"name": "Roon volume", "replaces": "volume.set", "match": ["roon volume (?P<n>\\d+)"], "run": "roonctl volume {n}"},
  {"name": "Projector", "say": ["projector on", "turn on the projector"], "run": "~/bin/projector on"}
]
```

The owner edits `voice_commands` both ways: by hand in `config.json`, and in the Settings editor. The server reads
`config.json` once at start (`app/server.py:258`), so a hand edit takes effect after `void restart`. A Settings save
takes effect at once through `save_config` (`app/server.py:2781`). Whether `/opt/homebrew/bin` is on the server's PATH
when the LaunchAgent starts it (`app/server.py:485`) is unmeasured. `docs/GUIDE.md` tells the owner to give an absolute
path when the name alone isn't found, and to double each backslash of a pattern written by hand in JSON.

## Homes

| Shared concern | Its one home | What the home forbids elsewhere |
|---|---|---|
| Running a helper and reading its output | `procs.run` | `subprocess.run(..., capture_output=True, timeout=...)` wrappers in `app/`, other than `server._run` (`app/server.py:799`) and `winsys.ps` (`app/winsys.py:22`), which stay as they are |
| Starting a detached helper | `procs.spawn` | `Popen(..., DEVNULL, start_new_session=True)` outside `procs` |
| Process groups, stopping them | `procs.own_group_kw`, `procs.kill_tree`, `procs.stop_group` | `os.killpg`, `taskkill`, creationflags `0x200` outside `procs` |
| A child's UTF-8 locale | `procs.utf8_env` | setting `LANG` for a child anywhere else |
| Running a command line through a shell, and quoting a value into one | `procs.shell_argv`, `procs.quote` | `shell=True`, `sh -c` or `powershell -Command` built outside `procs`, other than `winsys.ps` (`app/winsys.py:22`); a value filled into a command line without `procs.quote` |
| Reading a request before matching | `spoken.normalize` | stripping the wake word, "please" or "can you" in Python anywhere else |
| Built-in instant actions and their names | `quick.INTENTS`, `quick.match`, `quick.act` | a built-in matcher outside `quick`; an intent name not in `INTENTS` |
| The owner's commands: shape, validation, phrase and pattern lookup, running | `commands` (`load`, `find`, `override`, `run`) | reading `cfg["voice_commands"]` except through `commands.load`; compiling an owner's pattern anywhere else; storing an entry `load` rejects |
| Which instant handler answers, in what order | `commands.handle` | the server choosing between `recall`, the user commands and `quick` itself (`app/server.py:3920-3923`) |
| The `voice_commands` default | `server.DEFAULTS` | a second default for it |
| The instant reply shape `{"say","mood","sfx"?,"cd"?}` | `app/quick.py:3-4` | a reply key the page does not read (`app/static/index.html:2147`) |
| Config in tests | a dict passed as `cfg` to `commands.handle` / `commands.load` | a test that writes the real `config.json` or imports `server` for these modules |

## Order

Each step has one done-check and one commit. `implementer` writes `app/` and `docs/`; `test-writer` writes `tests/`.

1. Null stubs of `procs` and `spoken`, exactly as in **Modules**. Paths: `app/procs.py`, `app/spoken.py`. Agent:
   `implementer`. Done: both import; suite green.
2. Tests of `procs` and `spoken` behavior. Paths: `tests/test_procs.py`, `tests/test_spoken.py`. Agent: `test-writer`.
   Done: the new tests fail on the stubs; the rest of the suite stays green.
3. `procs` and `spoken` bodies. Paths: `app/procs.py`, `app/spoken.py`. Agent: `implementer`. Done: suite green.
4. Move the copies onto the core: every replaced line under `procs` and `spoken` in **Modules**. Paths:
   `app/agents.py`, `app/server.py`, `app/quick.py`, `app/macsys.py`, `app/recall.py`. Agent: `implementer`. Done:
   suite green; no `_run`, `kill`, `spawn_kw`, `kill_tree` or `own_group_kw` defined outside `app/procs.py`, and no
   wake-word strip outside `app/spoken.py`.
5. Null stubs of `Intent`, `INTENTS`, `match` and `act` beside the working `handle`. Path: `app/quick.py`. Agent:
   `implementer`. Done: suite green.
6. Tests of the intents: each built-in phrase gives its intent and args, `act` gives the reply `handle` gives now.
   Path: `tests/test_quick_intents.py`. Agent: `test-writer`. Done: the new tests fail on the stubs; the rest stays
   green.
7. `match` and `act` bodies, from the matchers and actions of `app/quick.py:358-427`. `handle` becomes
   `act(match(spoken.normalize(text)))` until step 10. Path: `app/quick.py`. Agent: `implementer`. Done: suite green.
8. Null stubs of `commands`, exactly as in **Modules**. Path: `app/commands.py`. Agent: `implementer`. Done: imports;
   suite green.
9. Tests of `commands` behavior: loading and its skip reasons, phrase and pattern lookup, overrides, running a
   command line with its fields filled, a failed command's reply, the dispatch order.
   Path: `tests/test_commands.py`. Agent: `test-writer`. Done: the new tests fail on the stubs; the rest stays green.
10. `commands` bodies; the server wiring in **Modules**; `quick.handle` removed; the GUIDE's "Things he does
    instantly" (`docs/GUIDE.md:62-79`) and config table (`docs/GUIDE.md:238-260`) describe `voice_commands`. Paths:
    `app/commands.py`, `app/server.py`, `app/quick.py`, `docs/GUIDE.md`. Agent: `implementer`. Done: suite green; with
    the Roon pause entry in config, "hey Void, pause the music" posted to `/api/quick` runs `roonctl pause` and never
    `macsys.media`.
11. A page test of the Settings editor: a command added there is saved through `/api/settings` and listed back; a
    rejected entry shows its why. Path: `tests/test_page_commands.py`. Agent: `test-writer`. Done: the test fails on
    the current page; the other page tests stay green.
12. The editor in Settings → Brain, beside projects (`app/static/index.html:2706-2708`): name, phrases, patterns, an
    override picker filled from `INTENTS`, the command line, the reply; errors from `voice_command_errors`. Path:
    `app/static/index.html`. Agent: `implementer`. Done: step 11's test and the other page tests green.

## Decisions for the owner

1. **The shell a command line runs in on Windows.** Recommend PowerShell, the shell `winsys.ps` already runs
   (`app/winsys.py:25`), with values quoted as single-quoted strings. Alternative: `cmd /c`. Cost of the
   recommendation: PowerShell's start time on each command, unmeasured, and command lines written in PowerShell syntax.
   Cost of the alternative: cmd has no quoting that holds every value from speech (`%` and `"` stay live), so a field
   filled from speech can inject.
2. **When a hand edit of `config.json` takes effect.** Recommend at once: before each `/api/quick` the server rereads
   `voice_commands` from `config.json` when the file's mtime has changed since its last read or save. Alternative:
   after `void restart`, as now (`app/server.py:258`). Cost of the recommendation: one `stat` per request, unmeasured,
   and a reload path in the config home beside `save_config` (`app/server.py:2781`). Cost of the alternative: a
   restart after every hand edit, and a hand edit of `voice_commands` made while Void runs is overwritten by the next Settings save of the commands, which
   writes the in-memory list over the file's (`app/server.py:2784-2791`).
