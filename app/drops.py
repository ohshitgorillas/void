"""Everything Void's hearing dropped, read back off a server log, and what gate.judge does with each one now.

    void drops [LOG] [--day YYYY-MM-DD]

LOG is ~/.local/share/void/server.log unless named. --day keeps only lines stamped that day (server.hear_out stamps
every hear and verdict line); without it every drop in the log is listed, stamped or not. Each drop prints as

    <line>  <time>  <why> (<kind>)  ->  <now>  <what was heard>

where <now> is "KEPT" when today's gate would keep it, "drops: <why>" when it still drops, or "as logged" when the
log doesn't hold what the check needs (echo needs his words, low confidence needs Whisper's numbers, a sentence
looping needs more than the 80 characters the log keeps). Older logs, from
before the stamp, are read too: their lines name the drop in words of their own ("ignored while talking", "dropped
follow-up, not your voice (voice 0.43)"), mapped here onto gate.WHY.
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
UNSEEN = {"echo", "no speech", "low confidence"}  # drops whose inputs the log doesn't hold
CUT = 80                                          # the log keeps this many characters of what was heard


@dataclass(frozen=True)
class Drop:
    line: int        # 1-based line number in the log
    at: str          # the stamp, or "" on a line from before it
    why: str         # one of gate.WHY, or a drop no check makes any more (GONE)
    kind: str        # the burst's kind ("?" when the log doesn't say)
    text: str        # what was heard (the log keeps the first 80 characters)
    now: str         # "kept" (or "kept: stops him"), the reason it still drops, or "as logged"


def parse(rest):
    """A log line's words after '[void] ' and the stamp → (why, kind or None, text), or None when it isn't a drop."""
    for pat, why, kind in OLD:
        m = pat.match(rest)
        if m:
            return why or m.group("why"), kind, m.group("text")
    m = VERDICT.match(rest)
    if m and m.group("why") != "kept" and (m.group("why") in gate.WHY or m.group("why") in GONE):
        return m.group("why"), m.group("kind"), m.group("text")
    return None


def _kind(flags):
    """The kind a heard line's flags imply, for a drop line that doesn't name its own."""
    return "follow" if "follow-up" in flags else "over" if "while talking" in flags else "wake"


def now(why, kind, text, talking=False):
    """What gate.judge makes of a logged drop today, from what the log holds (`talking`: he still was when it was
    judged, as its heard line says)."""
    if why in UNSEEN or (why == "noise" and len(text) >= CUT):   # (a sentence looping needs all of it)
        return "as logged"
    # (a burst that reached its check had speech enough; Whisper's numbers aren't logged, so a follow-up is judged on
    # its words, which is how it reached the voiceprint: its confidence had passed)
    b = gate.Burst(text=text, heard=None, speech=1.0, seconds=1.0, kind=kind, talking=talking)
    v = gate.judge(b, [], {"voice_gate": True})
    return ("kept" if v.act != "barge" else "kept: stops him") if v.keep else v.why


def replay(lines, day=None):
    """Every drop in `lines` (a log's lines, in order), as Drops. `day`: only lines stamped that day."""
    out, flags = [], ""
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
        if got is None or (day and not at.startswith(day)):
            continue
        why, kind, text = got
        kind = kind or _kind(flags)
        out.append(Drop(n, at, why, kind, text, now(why, kind, text, "while talking" in flags)))
    return out


def report(drops):
    """The drops as lines to print: one per drop, then a count per reason and of those now kept."""
    rows = [f"{d.line:>6}  {d.at or '-':19}  {d.why} ({d.kind})  ->  "
            f"{d.now.upper() if d.now.startswith('kept') else d.now if d.now == 'as logged' else 'drops: ' + d.now}"
            f"  {d.text}"
            for d in drops]
    counts = {}
    for d in drops:
        counts[d.why] = counts.get(d.why, 0) + 1
    rows.append("")
    rows += [f"{n:>6}  {why}" for why, n in sorted(counts.items(), key=lambda x: -x[1])]
    rows.append(f"{len(drops):>6}  dropped in all; {sum(d.now.startswith('kept') for d in drops)} of them kept now")
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
