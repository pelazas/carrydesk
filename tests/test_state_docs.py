"""The state docs must not contradict themselves or the plan.

`AGENTS.md` exists for one reason: an agent that has never seen this project
reads it and learns what is true. Today it said, in a status table near the top,
that mainnet payments were live with settlements confirmed on-chain -- and then
said, 190 lines further down, "Not yet verified: an actual mainnet settlement.
Nobody has run one." Both sentences had been true when written. Only one still
was, and which answer a reader got depended on where they happened to look.

`STATUS.md` had the mirror problem: a "Next up" list whose items 2, 3 and 4
(make the repo public, mainnet payments, listings) were all shipped hours
earlier. A plan that lists finished work is not merely untidy -- it is a
instruction to redo it, aimed at whoever picks this up cold.

Neither is catchable by reading carefully, because the sentence is correct when
you write it and wrong later, in a file nobody rereads. So both rules are
checked here instead:

1. no sentence may claim a capability is unverified while the status table marks
   that same capability shipped;
2. no item in the forward plan may name a capability the status table marks
   shipped;
3. no doc may assert a settlement count, because it decays on the next call --
   `scripts/revenue.py` reports it instead.

Dated entries in STATUS.md are a changelog, not a claim about now, and are
exempt from (1) and (3) -- "two settlements" under a 2026-08-02 heading is a
record of that day, and rewriting history to stay current would destroy the
thing the archive exists to prove.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent
AGENTS = ROOT / "AGENTS.md"
STATUS = ROOT / "STATUS.md"

# Phrases that assert something has NOT happened yet. Deliberately narrow:
# "without", "unless" and friends appear in correct conditional prose
# ("mainnet without keys raises at startup") and must not trip this.
NEGATIONS = [
    r"not yet verified",
    r"not yet built",
    r"not yet run",
    r"not yet done",
    r"nobody has",
    r"no one has",
    r"has never been",
    r"yet to be",
]

STOPWORDS = {"the", "a", "an", "and", "of", "data", "server", "service"}

# Distribution is the one row deliberately marked ⚠️, and saying so is the most
# important honest sentence in the repo -- "nobody has posted about it" must
# stay sayable. A negation carrying any of these is about attention, not about
# whether a capability works, so it is not a contradiction of a ✅ row.
PROMOTION_WORDS = {
    "posted", "posting", "post", "promoted", "promote", "promotion", "shared",
    "tweeted", "arrived", "traffic", "attention", "users", "customers", "demand",
    "external", "bought", "paid us",
}


def shipped_capabilities() -> dict[str, set[str]]:
    """Rows of the AGENTS.md status table marked ✅, as keyword sets.

    A row reading "| Mainnet payments | ✅ live … |" yields {"mainnet",
    "payments"}. ⚠️ rows are excluded: Distribution is legitimately still open
    and the plan is supposed to talk about it.
    """
    out: dict[str, set[str]] = {}
    for line in AGENTS.read_text().splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$", line)
        if not m:
            continue
        label, state = m.group(1), m.group(2)
        if "✅" not in state or label.lower() in ("piece", "surface"):
            continue
        words = {w for w in re.findall(r"[a-z0-9]+", label.lower()) if w not in STOPWORDS}
        if words:
            out[label] = words
    return out


def undated_prose(md: str) -> list[str]:
    """Everything outside a dated `## YYYY-MM-DD` changelog entry.

    A dated section records what was true on that date and is allowed to stay
    that way; only prose claiming to describe *now* is held to the rules.
    """
    before_first_entry = re.split(r"^## \d{4}-\d{2}-\d{2}.*$", md, flags=re.M)[0]
    return re.split(r"(?<=[.!?])\s+", before_first_entry)


def test_the_table_parser_actually_finds_rows():
    """A scanner that matches nothing would pass forever."""
    caps = shipped_capabilities()
    assert len(caps) >= 5, f"only parsed {caps}"
    assert any("mainnet" in w for w in caps.values()), "lost the mainnet row"


@pytest.mark.parametrize("pattern", NEGATIONS)
def test_no_sentence_denies_what_the_status_table_confirms(pattern):
    caps = shipped_capabilities()
    for sentence in undated_prose(AGENTS.read_text()):
        low = sentence.lower()
        if not re.search(pattern, low):
            continue
        if PROMOTION_WORDS & set(re.findall(r"[a-z]+", low)):
            continue  # a true statement about the ⚠️ row, not a contradiction
        for label, words in caps.items():
            # ANY keyword, not all: the real bug read "Not yet verified: an
            # actual mainnet settlement", which names the row's subject
            # ("mainnet") without repeating its label ("payments").
            if words & set(re.findall(r"[a-z0-9]+", low)):
                pytest.fail(
                    f"AGENTS.md says {label!r} is shipped (✅) but also says:\n"
                    f"  {sentence.strip()[:160]}\n"
                    f"One of the two is stale; a reader gets whichever they find first."
                )


def plan_items() -> list[str]:
    """The bolded lead of each numbered item under STATUS.md's `## Next up`.

    Only the lead, not the body: an item is allowed to *reference* shipped work
    as context ("the MCP server is installable from PyPI"); what it must not do
    is propose it as work to do.
    """
    md = STATUS.read_text()
    m = re.search(r"^## Next up.*?$(.*?)^## ", md, flags=re.M | re.S)
    assert m, "STATUS.md lost its `## Next up` section"
    return re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", m.group(1), flags=re.M)


def test_the_plan_parser_actually_finds_items():
    items = plan_items()
    assert items, "parsed no plan items -- the guard below would be vacuous"


def test_the_plan_does_not_propose_already_shipped_work():
    caps = shipped_capabilities()
    for item in plan_items():
        words = set(re.findall(r"[a-z0-9]+", item.lower()))
        for label, kw in caps.items():
            assert not (kw <= words), (
                f"STATUS.md plans {item!r} but the AGENTS.md table marks "
                f"{label!r} shipped (✅). Delete the item or un-tick the row."
            )


def test_no_doc_asserts_a_settlement_count():
    """Counts decay silently; `scripts/revenue.py` reads them from Base."""
    bad = re.compile(
        r"\b(one|two|three|four|five|six|\d+)\s+(mainnet\s+)?settlements?\b", re.I
    )
    for path in (AGENTS, STATUS):
        for sentence in undated_prose(path.read_text()):
            m = bad.search(sentence)
            assert not m, (
                f"{path.name} states {m.group(0)!r} outside a dated entry. That number "
                f"is wrong as soon as another call settles -- point at "
                f"scripts/revenue.py instead."
            )


def test_the_revenue_script_is_the_documented_source_of_truth():
    assert (ROOT / "scripts" / "revenue.py").exists()
    assert "revenue.py" in AGENTS.read_text(), (
        "AGENTS.md must tell the next agent where the real number lives"
    )
