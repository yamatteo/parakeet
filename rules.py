"""Rules for a context-sensitive grammar.

Context-sensitive grammars have rules like
    b C a  →  b D E a
    here represented as
    &b〈 C → D E 〉&a
which means that 'C' can be replaced by 'DE' (or 'DE' can match to a 'C') only
if it is preceded by a 'b' and followed by an 'a'. This is represented by
having a context-free rule 〈 C → D E 〉 with additional expectation &b on the
left and &a on the right. These expectations are not enforced when the rule is
used but on subsequent match: suppose there is a match for &b〈 C → D E 〉&a
and there are the rules
    S  →  z C
    R  →  b C
The rule for 'S' does not match because 'z' does not satisfy the expectations
of 'C'. The rule for 'R' match, quench the left expectation for 'b' and
inherit the right expectation for 'a'.
Expectations can be either positive (i.e. &b accept only a match with external
'b') or negative (i.e. !b accept any match but the ones with external 'b').

The other type of rules are terminal rules that match directly to the input
(a string) using a regular expression. They are here represented by
    〈 a → /some regular expression/ 〉

Examples:
    Terminal rule are defined in the following way:
        TR(ext="a", act=r"a[^a]+a")                  is rule〈 a → /a[^a]+a/ 〉

    Substitution rules are defined as follows:
        SR(ext="S", act=("a", "b"))                        is rule〈 S → a b 〉
        SR(ext="S", act=("a",), right=EX("&", "b"))        is rule〈 S → a 〉&b
        SR(ext="S", act=("a",), left=EX("!", "a"), right=EX("&", "b"))
            is rule !a〈 S → a 〉&b which means:
            an 'S' can turn into an 'a'
            if it is followed by a 'b' and not preceded by an 'a'
            or, conversely,
            an 'a' can be parsed as an 'S' under the same conditions
"""

# regex is favored over re because of its unicode support
import regex as re

from typing import Sequence, Optional, Literal
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """Base class for rules.

    Useful to simplify type checking of rules. It is not to be instantiated
    directly. It has to be frozen, i.e. hashable, because rules are to be
    included in their matches and matches are to be stored in a set.
    """

    # ext stand for 'external', the left-hand side of a substitution rule. It
    # is the name that will be given to the eventual match.
    ext: str

    def __hash__(self):
        return hash((
            getattr(self, "ext"),
            getattr(self, "act"),
            getattr(self, "left", None),
            getattr(self, "right", None),
        ))


@dataclass(frozen=True)
class TR(Rule):
    """Class for terminal rule.

    Attributes:
        ext (str): external name of the resulting match
        act (str): activation pattern to be compiled with re.compile(act)
        regex (re.Pattern): result of re.compile(act) is what does the actual
            pattern matching
    """

    act: str
    regex: re.Regex = None

    # Dataclasses already have an __init__ method, but it calls
    # __post_init__ if it is defined
    def __post_init__(self):
        """Compile self.act and store it in self.regex, just after __init__."""

        # object.__setattr__ is used because TR is frozen and TR.__setattr__
        # refuse to assign values
        object.__setattr__(self, "regex", re.compile(self.act))

    def __repr__(self):
        return f"〈{self.ext} → /{self.act}/〉"


@dataclass(frozen=True)
class EX:
    """Class for rule expectations.

    See module docstring for the meaning of expectations in
    context-sensitive grammars.

    Attributes:
        type (str): can be either '&' for a positive expectation or '!' for a
            negative expectation
        ext (str): the external of the match that is expected
    """

    type: Literal["&", "!"]
    ext: str

    def __repr__(self):
        return self.type + self.ext

    def __call__(self, external: str):
        """Shortcut to check expectation."""
        if self.type == "&":
            return self.ext == external
        else:
            return self.ext != external

    def __iter__(self):
        return iter((self.type, self.ext))


@dataclass(frozen=True)
class SR(Rule):
    """Class for substitution rules.

    Attributes:
        ext (str): external name of the resulting match
        act (Sequence[str]): sequence of external that are expected (as a
            sequence of complete matches with such externals) to make the
            substitution
        left (EX, optional): left expectation if present, None otherwise
        right (EX, optional): right expectation if present, None otherwise
    """

    act: Sequence[str]
    left: Optional[EX] = None
    right: Optional[EX] = None

    def __repr__(self):
        left = str(self.left) if self.left else ''
        right = str(self.right) if self.right else ''
        return f"{left}〈{self.ext} → {' '.join(self.act)}〉{right}"
