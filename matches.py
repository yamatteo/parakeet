"""Matches from a context-sensitive grammar.

Context-sensitive grammars have rules like
    b C a  →  b D E a
    here represented as
    &b〈 C → D E 〉&a
which means that 'C' can be replaced by 'DE' (or 'DE' can match to a 'C') only
if it is preceded by a 'b' and followed by an 'a'. If such match is possible it
is created with information about the rule used, its children (i.e. D end E)
and its context (i.e. a b on the left and an a on the right. As in Earley's
algorithm, matches are constructed step by step, from left to right. So,
in order:
 - check if a match with external 'b' is present; is so create an incomplete
   forward match *b ( C → · D E ) &a where
    - '*b' is a reference to the left-brother of the new match (i.e. a complete
      match that serves as context on the left)
    - the bullet · separate the completed matches (here none) from the
      awaited ones (here D and E)
    - '&a' is the expectation of the match, what is needed as context on the
      right after completion
 - when a match with external 'D' is completed, check if b (the
   left-brother) and D can concatenate; if so, create match *b ( C → D · E ) &a
 - when a match 'E' is completed, check if D and E can concatenate; if so
   create match *b ( C → D E · ) &a
 - when a match 'a' is completed, check if E and a can concatenate; if so
   create the complete match *b (( C → D E )) *a; this match starts where D
   starts and ends where E ends, but it remember that it needs b on the left
   and a on the right to be constructed.
"""

from dataclasses import dataclass, field
from typing import Sequence, Union, Optional
from math import ceil, log

from rules import TR, SR


class CyclicMatchError(Exception):
    """Exception when a match would be a useless renaming of itself."""


@dataclass(frozen=True)
class Match:
    """Base class for matches.

    Matches are frozen dataset because they are immutable and hashable to store
    them without duplicates. Only the bytes representation of the match is used
    to determine equality and to hash the match.

    Some matches have a left-brother or a right-brother. In a context-sensitive
    grammar some rule can create a match only when there is some other match on
    the left and/or on the right. This context is remembered in the match
    itself by a reference to what match was on the left and what match was on
    the right at the time of its formation.

    Attributes:
        rule: every match is formed by one rule;
        start: position in the parsing string where begins the first terminal
            match used in constructing the current match;
        close: position in the parsing string where ends the last terminal
            match used in constructing the current match;
        name: the bytes representation of the rule, assigned by the parser;
            names of terminal matches also include their start and their close;
        crepr: the bytes representation of this match and all its children in
            reverse polish notation;
        lrepr: the bytes representation the left-brother of this match and all
            its left-brothers recursively;
        rrepr: the bytes representation the right-brother of this match (when
            it is present, i.e. only for some CompleteMatch) and all its
            right-brothers recursively;
        children: the matches that where consumed to form this one;
        lbro: the match present on the left of this one at the time of its
            formation;

    """

    rule: Union[SR, TR] = field(compare=False)
    start: int = field(compare=False)
    close: int = field(compare=False)
    name: bytes = field(compare=False)
    crepr: bytes = field(default=bytes(), compare=True)
    lrepr: bytes = field(default=bytes(), compare=True)
    rrepr: bytes = field(default=bytes(), compare=True)
    children: Sequence["CompleteMatch"] = field(default=tuple(), compare=False)
    lbro: Optional["CompleteMatch"] = field(default=None, compare=False)

    def __post_init__(self):
        """Calculates bytes representation of the match."""

        # object.__setattr__ is used because matches are frozen and __setattr__
        # refuse to assign values

        # The central representation is made joining the name of the rule (
        # assigned by the parser) with the central representations of all the
        # children, in reverse polish notation. In this way it is possible to
        # avoid parenthesis and save some bytes.
        object.__setattr__(
            self, "crepr",
            self.name + bytes().join(cm.crepr for cm in self.children)
        )

        # If there is a left-brother, the left representation is the central
        # representation of the left-brother preceded by its left
        # representation. In this way every relevant match in the left
        # context is accounted for.
        lb = getattr(self, "lbro", None)
        if lb is not None:
            object.__setattr__(
                self, "lrepr",
                lb.lrepr + lb.crepr
            )

        # When the match is to be build upon some previous match,
        # this information is also recorded in the left representation to
        # distinguish it from a similar match without such restriction.
        upon = getattr(self, "upon", None)
        if upon is not None:
            object.__setattr__(
                self, "lrepr",
                self.lrepr + upon.crepr
            )

        # If there is a right-brother, the right representation is the central
        # representation of the right-brother followed by its right
        # representation. In this way every relevant match in the right context
        # is accounted for.
        rb = getattr(self, "rbro", None)
        if rb is None and len(self.children) > 0:
            rb = getattr(self.children[-1], "rbro", None)
        if rb is not None:
            object.__setattr__(
                self, "rrepr",
                rb.crepr + rb.rrepr
            )

    @property
    def external(self) -> str:
        """Shortcut to the rule external."""
        return self.rule.ext

    @property
    def expectation(self):
        """What the match needs as context on the right side."""
        return getattr(self.rule, "right", None)

    @property
    def first(self):
        """Shortcut to the leftmost child."""
        return self.children[0]

    @property
    def last(self):
        """Shortcut to the rightmost child."""
        return self.children[-1]


@dataclass(frozen=True)
class CompleteMatch(Match):
    """A match with all its children.

    A complete match remembers the context of its formation with its
    left-brother and right-brother. Therefore a complete match can effectively
    be constructed.

    Attributes:
        rbro: the match used as context on the right side;
    """
    rbro: Optional["CompleteMatch"] = field(default=None, compare=False)

    def __repr__(self):
        left = f"*{self.lbro.external}{self.lbro.depth} " \
            if self.lbro is not None else ''
        ext = self.external
        if len(self.children) > 0:
            children = ' '.join([match.external for match in self.children])
        else:
            children = "/.../"
        depth = self.depth
        right = f" *{self.rbro.external}{self.rbro.depth}" \
            if self.rbro is not None else ''
        s = self.start
        c = self.close
        return f"{left}(({ext} → {children})){depth}{right} [{s}:{c}]"

    @property
    def depth(self):
        """Helper for human-readable repr."""
        return len(self.wrapping_history())

    @classmethod
    def from_scan(cls, rule: TR, string: str, start: int, name: bytes) \
            -> "CompleteMatch":
        """Create a terminal match scanning from string[start:].

        This is the 'scan' step in the Early algorithm."""
        assert (match := rule.regex.match(string[start:])) is not None
        return cls(
            rule=rule,
            start=start,
            close=start + match.end(),
            name=(name + to_bytes(start, len(string) + 1)
                  + to_bytes(start + match.end(), len(string) + 1)),
        )

    @classmethod
    def from_forward(cls, fm: "ForwardMatch") -> "CompleteMatch":
        """Create a complete match from a complete forward match."""
        # fm has all its required children
        assert len(fm.awaited) == 0

        # fm does not have an unmet expectation on the right
        # Implicit: negative lookaheads needs something on the right
        rb = fm.last.rbro
        assert fm.rule.right is None \
               or (rb is not None and fm.rule.right(rb.external))

        return cls(
            rule=fm.rule,
            start=fm.start,
            close=fm.close,
            name=fm.name,
            children=fm.children,
            lbro=fm.lbro,
            rbro=rb,
        )

    def wrapping_history(self) -> Sequence["CompleteMatch"]:
        """All wrapping matches, from the newest to the first.

        A wrapping is a match with only one child, so basically just changing
        the external of the match.
        """
        if len(self.children) != 1:
            return self,
        else:
            return self, *self.first.wrapping_history()


@dataclass(frozen=True)
class ForwardMatch(Match):
    """An incomplete match.

    Attributes:
        upon: if not None, force the forward match to be constructed upon some
            other match;
    """
    upon: Optional["CompleteMatch"] = field(default=None, compare=False)

    def __repr__(self):
        left = f"*{self.lbro.external}{self.lbro.depth} " \
            if self.lbro is not None else ''
        left += f">{self.upon.external}{self.upon.depth} " \
            if self.upon is not None else ''
        ext = self.external
        children = ' '.join([match.external for match in self.children])
        awaited = ' '.join(self.awaited)
        right = f" {self.expectation}" if self.expectation is not None else ''
        s = self.start
        c = self.close
        return f"{left}({ext} → {children} • {awaited}){right} [{s}:{c}]"

    @property
    def awaited(self) -> Sequence[str]:
        """The externals that are awaited to have a complete match."""
        return self.rule.act[len(self.children):]

    @property
    def depth(self) -> int:
        """Helper for match human-readable repr."""
        return 0

    @classmethod
    def from_rule(cls, rule: SR, start: int, name: bytes,
                  left_brother: Optional["CompleteMatch"] = None,
                  upon: Optional["CompleteMatch"] = None, ) \
            -> "ForwardMatch":
        """Shortcut to spawn incomplete match.

        This is the 'prediction' step in the Early algorithm.
        """
        return cls(
            rule=rule,
            start=start,
            close=start,
            name=name,
            children=tuple(),
            lbro=left_brother,
            upon=upon,
        )


def to_bytes(i: int, _max: int):
    """Convert integer to bytes sequence of fixed length."""
    length = ceil(log(_max, 256))
    return i.to_bytes(length=length, byteorder='big')
