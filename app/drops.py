"""Every heard burst of a server log, kept or dropped, read back, and what gate.judge does with each one now.

    void drops [LOG] [--day YYYY-MM-DD]

LOG is ~/.local/share/void/server.log unless named. --day keeps only lines stamped that day (server.hear_out stamps
every hear and verdict line); without it every verdict line in the log is listed, stamped or not. Each prints as

    <line>  <time>  <why> (<kind>)  ->  <now>  <what was heard>

where <why> is the verdict as logged ("kept" for a burst that got through) and <now> is "KEPT" when today's gate would
keep it, "drops: <why>" when it drops, or "as logged" when the log doesn't hold what the check needs (an echo drop heard
with his voice in the air needs his words, which the log doesn't keep; low confidence needs Whisper's numbers, a sentence
looping needs more than the 80 characters the log keeps). An echo drop whose own heard line shows it clear of him is
judged again, as heard after he went quiet (echo is only ever judged on a burst that rang); one with no heard line of
its own is "as logged", because nothing in the log shows it clear of him.
Older logs, from before the stamp, are read too, for their drops: their lines name the drop in words of their own
("ignored while talking", "dropped follow-up, not your voice (voice 0.43)"), mapped here onto gate.WHY. Their kept lines
("follow-up request ...") are not listed.
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402

LOG = Path.home() / ".local" / "share" / "void" / "server.log"
LINE = re.compile(r"^\[void\] (?:(?P<at>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) )?(?P<rest>.*)$")
HEARD = re.compile(r"^heard [\d.]+s, \d+ words(?P<flags>.*)$")
SCORE = r"(?: \(voice (?:[\d.]+|n/a)\))?"
VERDICT = re.compile(r"^(?P<why>[a-z ]+?)(?: \((?P<kind>listen|wake|follow|over|peek)\))?" + SCORE + r": (?P<text>.*)$")
# the words older servers logged a drop in → (gate.WHY, or None: the line names it · kind, or None: the heard line
# before it says)
OLD = [(re.compile(r"^dropped follow-up, (?P<why>[a-z ]+?)" + SCORE + r": (?P<text>.*)$"), None, "follow"),
       (re.compile(r"^ignored while talking: (?P<text>.*)$"), "while talking", "over"),
       (re.compile(r'^ignored: no "hey Void": (?P<text>.*)$'), "no wake word", "wake"),
       (re.compile(r"^ignored stray word: (?P<text>.*)$"), "stray word", "follow"),
       (re.compile(r"^dropped as noise: (?P<text>.*)$"), "noise", None),
       (re.compile(r"^dropped echo of own speech: (?P<text>.*)$"), "echo", None)]
GONE = {"not your voice", "stray word"}           # drops no check makes any more
UNSEEN = {"no speech", "low confidence"}  # drops whose inputs the log doesn't hold (echo: only when it rang, see now)
CUT = 80                                          # the log keeps this many characters of what was heard


@dataclass(frozen=True)
class Drop:             # (one row of the report: a drop, or a burst the log kept)
    line: int        # 1-based line number in the log
    at: str          # the stamp, or "" on a line from before it
    why: str         # one of gate.WHY ("kept" among them), or a drop no check makes any more (GONE)
    kind: str        # the burst's kind ("?" when the log doesn't say)
    text: str        # what was heard (the log keeps the first 80 characters)
    now: str         # "kept" (or "kept: stops him"), the reason it still drops, or "as logged"


def parse(rest):
    """A log line's words after '[void] ' and the stamp → (why, kind or None, text), or None if it isn't a verdict."""
    for pat, why, kind in OLD:
        m = pat.match(rest)
        if m:
            return why or m.group("why"), kind, m.group("text")
    m = VERDICT.match(rest)
    if m and (m.group("why") in gate.WHY or m.group("why") in GONE):
        return m.group("why"), m.group("kind"), m.group("text")
    return None


def _kind(flags):
    """The kind a heard line's flags imply, for a drop line that doesn't name its own."""
    return "follow" if "follow-up" in flags else "over" if "while talking" in flags else "wake"


def rang(flags: str, kind: str) -> bool:
    """The one reading of a logged burst's flags: it was heard with his sound, or its ring, in the air."""
    return kind in ("over", "peek") or any(f in flags for f in ("while talking", "after his last word", "in his echo"))


def now(why, kind, text, talking=False, rang=True):
    """What gate.judge makes of a logged verdict today, from what the log holds (`talking`: he still was when it was
    judged, as its heard line says; `rang`: his sound or its ring was in the air, as drops.rang reads it)."""
    if why in UNSEEN or (why == "echo" and rang):         # (an echo that rang needs his words, which the log lacks)
        return "as logged"
    # (a burst that reached its check had speech enough; Whisper's numbers aren't logged, so a follow-up is judged on
    # its words, which is how it reached the voiceprint: its confidence had passed)
    b = gate.Burst(text=text, heard=None, speech=1.0, seconds=1.0, kind=kind, talking=talking, rang=rang)
    v = gate.judge(b, [], {"voice_gate": True})
    if len(text) >= CUT and (why == "noise" or (why == "kept" and v.why == "noise")):
        return "as logged"       # (a sentence looping needs all of it)
    return ("kept" if v.act != "barge" else "kept: stops him") if v.keep else v.why


def replay(lines, day=None):
    """Every verdict line in `lines` (a log's lines, in order), kept or dropped, as Drops. `day`: only lines stamped
    that day."""
    out, flags = [], None                        # (flags: of the heard line just before this one, else None)
    for n, line in enumerate(lines, 1):
        m = LINE.match(line)
        if not m:
            continue
        at, rest = m.group("at") or "", m.group("rest")
        h = HEARD.match(rest)
        if h:
            flags = h.group("flags")
            continue
        got = parse(rest)
        if got is None:
            continue
        mine, flags = flags, None                # (a heard line pairs with the one verdict line after it)
        if day and not at.startswith(day):
            continue
        why, kind, text = got
        kind = kind or _kind(mine or "")
        # (no heard line of its own: nothing in the log shows it clear of him, so an echo replays as logged)
        out.append(Drop(n, at, why, kind, text, now(why, kind, text, "while talking" in (mine or ""),
                                                     mine is None or rang(mine, kind))))
    return out


def report(drops):
    """The rows as lines to print: one per burst, then a count per logged verdict, the rows in all and how many of the
    log's drops are kept now."""
    rows = [f"{d.line:>6}  {d.at or '-':19}  {d.why} ({d.kind})  ->  "
            f"{d.now.upper() if d.now.startswith('kept') else d.now if d.now == 'as logged' else 'drops: ' + d.now}"
            f"  {d.text}"
            for d in drops]
    counts = {}
    for d in drops:
        counts[d.why] = counts.get(d.why, 0) + 1
    rows.append("")
    rows += [f"{n:>6}  {why}" for why, n in sorted(counts.items(), key=lambda x: -x[1])]
    lost = [d for d in drops if d.why != "kept"]
    kept_now = sum(d.now.startswith("kept") for d in lost)
    rows.append(f"{len(drops):>6}  heard in all; {len(lost)} dropped, {kept_now} of them kept now")
    return rows


def main(argv):
    args, day = list(argv), None
    if "--day" in args:
        i = args.index("--day")
        day, args = args[i + 1], args[:i] + args[i + 2:]
    path = Path(args[0]) if args else LOG
    print("\n".join(report(replay(path.read_text(errors="replace").splitlines(), day))))


if __name__ == "__main__":
    main(sys.argv[1:])
