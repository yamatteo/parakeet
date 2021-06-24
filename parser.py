"""Parser for context-sensitive grammar with adapted Earley's algorithm.

    Create the parser with its rules in any order, for example:
    p = Parser([
            TR("a", r"a"),                          i.e. 〈 a → /a/ 〉
            TR("b", r"b"),                               〈 b → /b/ 〉
            TR("c", r"c"),                               〈 c → /c/ 〉
            SR("C", ("c",), left=EX("&", "b")),          〈 b C → b c 〉
            SR("C", ("c",), left=EX("&", "c")),          〈 c C → c c 〉
            SR("B", ("b",), left=EX("&", "a")),          〈 a B → a b 〉
            SR("B", ("b",), left=EX("&", "b")),          〈 b B → b B 〉
            SR("W", ("B",), right=EX("&", "C")),         〈 W C → B C 〉
            SR("Z", ("C",), left=EX("&", "W")),          〈 W Z → W C 〉
            SR("C", ("W",), right=EX("&", "Z")),         〈 C Z → W Z 〉
            SR("B", ("Z",), left=EX("&", "C")),          〈 C B → C Z 〉
            SR("S", ("a", "S", "B", "C")),               〈 S → a S B C 〉
            SR("S", ("a", "B", "C",)),                   〈 S → a B C 〉
        ])

    and parse strings with or without the expected non-terminal

        solutions = p.parse("aabbcc", expect='S')
        solutions = p.parse("aaaabbbbcccc")

    solutions is a list of complete matches that span the whole string. If
    the grammar has cycles, i.e. there are rules like 〈 A → B 〉, 〈 B → C 〉
    and 〈 C → A 〉, infinite renaming cycles are interrupted at the first
    reappearance of the same non-terminal.
"""

from typing import Sequence, Optional, Union

from rules import TR, SR
from matches import CyclicMatchError, CompleteMatch, ForwardMatch, to_bytes
from interactions import feed, settle, CyclicMatchError, history_at_close

CMorFM = Union[CompleteMatch, ForwardMatch]


class CompleteMatchStructure:
    """Store complete matches without duplicates."""

    def __init__(self, string: str, rules: Sequence[Union[TR, SR]]):
        # External None is added to have a fast way to select all complete
        # matches regardless of their external.
        externals = list({rule.ext for rule in rules}) + [None, ]

        # Indexes goes from 0 to len(string) included because sometimes a
        # request for a match with that start is issued, even if there
        # cannot be any.
        self.complete_matches = {i: {
            external: list() for external in externals
        } for i in range(len(string) + 1)}

        self.all_matches = list()

    def select(self, start: int, external: Optional[str]) \
            -> list[CompleteMatch]:
        """Select all complete matches with given start and given external."""
        return self.complete_matches[start][external]

    def add(self, match: CompleteMatch) -> bool:
        """Add a match if it is not present already, and tell if the
        operation really happened."""
        if match not in self.all_matches:
            self.all_matches.append(match)
            self.complete_matches[match.start][match.external].append(match)
            self.complete_matches[match.start][None].append(match)
            return True
        return False


class ForwardMatchStructure:
    """Store forward match, without duplicates."""

    def __init__(self, string: str, rules: Sequence[Union[TR, SR]]):
        externals = list({rule.ext for rule in rules})

        # Indexes goes from 0 to len(string) included because sometimes a
        # request for a match with that close is issued: when last match can
        # be obtained by rule with right expectation.
        self.forward_matches = {i: {
            external: list() for external in externals
        } for i in range(len(string) + 1)}
        self.all_matches = list()
        self.externals = externals

    def select(self, close: Optional[int], external: Optional[str]) \
            -> list[ForwardMatch]:
        """Select all complete matches with given start and given external."""
        return self.forward_matches[close][external]

    def add(self, match: ForwardMatch) -> bool:
        """Add a match if it is not present already, and tell if the
        operation really happened."""
        if match in self.all_matches:
            return False
        self.all_matches.append(match)
        if len(match.awaited) == 0:
            _type, ext = match.expectation
            if _type == "&":
                self.forward_matches[match.close][ext].append(match)
            else:
                for external in self.externals:
                    if match.expectation(external):
                        self.forward_matches[match.close][external] \
                            .append(match)
        else:
            self.forward_matches[match.close][match.awaited[0]].append(match)
        return True


class Parser:
    """Parser for context-sensitive grammar with adapted Earley's algorithm.

    Create the parser with its rules in any order, for example:
    p = Parser([
            TR("a", r"a"),                          i.e. 〈 a → /a/ 〉
            TR("b", r"b"),                               〈 b → /b/ 〉
            TR("c", r"c"),                               〈 c → /c/ 〉
            SR("C", ("c",), left=EX("&", "b")),          〈 b C → b c 〉
            SR("C", ("c",), left=EX("&", "c")),          〈 c C → c c 〉
            SR("B", ("b",), left=EX("&", "a")),          〈 a B → a b 〉
            SR("B", ("b",), left=EX("&", "b")),          〈 b B → b B 〉
            SR("W", ("B",), right=EX("&", "C")),         〈 W C → B C 〉
            SR("Z", ("C",), left=EX("&", "W")),          〈 W Z → W C 〉
            SR("C", ("W",), right=EX("&", "Z")),         〈 C Z → W Z 〉
            SR("B", ("Z",), left=EX("&", "C")),          〈 C B → C Z 〉
            SR("S", ("a", "S", "B", "C")),               〈 S → a S B C 〉
            SR("S", ("a", "B", "C",)),                   〈 S → a B C 〉
        ])

    and parse strings with or without the expected non-terminal

        solutions = p.parse("aabbcc", expect='S')
        solutions = p.parse("aaaabbbbcccc")

    solutions is a list of complete matches that span the whole string. If
    the grammar has cycles, i.e. there are rules like 〈 A → B 〉, 〈 B → C 〉
    and 〈 C → A 〉, infinite renaming cycles are interrupted at the first
    reappearance of the same non-terminal.
    """

    def __init__(self, rules: Sequence[Union[TR, SR]]):
        self.rules = rules
        self.namings = {
            rule: to_bytes(i, len(rules)) for i, rule in enumerate(rules)
        }

        externals = set.union({None}, {rule.ext for rule in rules})
        self.terminal_rules = {
            ext: {
                rule
                for rule in rules
                if isinstance(rule, TR) and (ext is None or rule.ext == ext)
            } for ext in externals
        }
        self.substitution_rules = {
            ext: {
                rule
                for rule in rules
                if isinstance(rule, SR) and (ext is None or rule.ext == ext)
            } for ext in externals
        }

        self.cms: Optional[CompleteMatchStructure] = None
        self.fms: Optional[ForwardMatchStructure] = None
        self.string = None

    def parse(self, string: str, expect: Optional[str] = None,
              verbose: bool = False) -> list[CompleteMatch]:
        """Parse the string using a sensitive version of Earley's algorithm."""
        self.cms = CompleteMatchStructure(string, self.rules)
        self.fms = ForwardMatchStructure(string, self.rules)
        self.string = string

        # forwards and completes contain the new matches that are not yet in
        # the match structures and need to be processed
        if expect is None:
            forwards = {
                ForwardMatch.from_rule(rule, 0, name=self.namings[rule])
                for rule in self.rules if isinstance(rule, SR)
            }
        else:
            forwards = {
                ForwardMatch.from_rule(rule, 0, name=self.namings[rule])
                for rule in self.substitution_rules[expect]
            }
        completes = set()

        while len(forwards) > 0 or len(completes) > 0:
            # choose and process a new match, all forwards first and then a
            # complete match if there is no new forward match
            try:
                new_matches = self.predict(forwards.pop(), verbose=verbose)
            except KeyError:
                new_matches = self.complete(completes.pop(), verbose=verbose)

            # add new matches to forwards and completes
            forwards.update({
                m for m in new_matches if isinstance(m, ForwardMatch)
            })
            completes.update({
                m for m in new_matches if isinstance(m, CompleteMatch)
            })

        # when there is no new match to be processed, a list of al the
        # complete matches that span the whole string is returned
        return list(
            match for match in self.cms.select(0, expect)
            if match.close == len(string)
        )

    def predict(self, fm: ForwardMatch, verbose: bool = False) -> set[CMorFM]:
        """Process a new forward match."""
        if not self.fms.add(fm):
            if verbose:
                print("Duplicate:", fm)
            return set()
        if verbose:
            print("PREDICT  from", fm)

        new_matches = set()
        try:
            awaited = fm.awaited[0]
        except IndexError:
            _type, ext = fm.expectation
            awaited = ext if _type == "&" else None

        # The eventual new match must be built upon some other match in two
        # cases:
        #   - there is no child yet but a match was provided in the
        #     definition of fm
        #   - the last child of fm need some right-brother as context on the
        #     right
        if len(fm.children) == 0 and fm.upon is not None:
            upon = fm.upon
        elif len(fm.children) > 0 and fm.last.rbro is not None:
            upon = fm.last.rbro
        else:
            upon = None

        # The eventual new match starts already with something on the left
        # that have to be its context on that side. If there is no children,
        # the context is given by fm's left-brother. If there are children,
        # the left context is the last child
        if len(fm.children) == 0:
            left_context = fm.lbro
        else:
            left_context = fm.last

        # When the grammar have cycles (there are rules like 〈 A → B 〉,
        # 〈 B → C 〉 and 〈 C → A 〉) it is possible that a forward match is
        # created after the complete match it needs. So the parser must try
        # with all relevant complete matches that start where fm closes.
        for cm in self.cms.select(fm.close, awaited):
            try:
                if len(fm.awaited) == 0:
                    new_matches.add(settle(fm, cm))
                else:
                    new_matches.add(feed(fm, cm))
            except AssertionError:
                pass
            except CyclicMatchError:
                if verbose:
                    print("    NOT upcycling", fm, cm)

        # If fm is waiting for a terminal the parser try to scan the string
        # with the relevant rules from the position where fm closes.
        for rule in self.terminal_rules[awaited]:
            try:
                new_matches.add(CompleteMatch.from_scan(
                    rule=rule,
                    string=self.string,
                    start=fm.close,
                    name=self.namings[rule],
                ))
            except AssertionError:
                pass

        # If fm is waiting for a non-terminal, for example if fm is ( S → A
        # · B C ), a new forward match will be created for every rule that
        # can deliver such non terminal, for example ( B → · b )
        for rule in self.substitution_rules[awaited]:
            if rule.left is not None:
                if left_context is None:
                    # This rule expect something but there is nothing on the
                    # left, so move on to the next rule
                    continue
                if rule.left(left_context.external):
                    # This rule as an expectation on the left that is met
                    # precisely by the left context, so it will be used as
                    # left-brother of the new forward match
                    left_brother = left_context
                else:
                    # The expectation of the rule is not met by the left
                    # context, but maybe it can be met by some previous
                    # match in the process of building the left context
                    for lb in history_at_close(left_context):
                        if rule.left(lb.external):
                            # lb satisfy rule's left expectation so it will
                            # be used as left-brother for the new forward
                            # match. This implies that the construction
                            # order is actually: first lb, then the new
                            # forward, then left_context and later fm.
                            left_brother = lb
                            break
                    else:
                        # Not left_context nor any of it previously built
                        # child can satisfy rule's expectation: move on to
                        # the next rule
                        continue

            else:
                # rule.left is None, whatever context is fine
                left_brother = left_context

            new_matches.add(
                ForwardMatch.from_rule(
                    rule=rule,
                    start=fm.close,
                    left_brother=left_brother,
                    upon=upon,
                    name=self.namings[rule]
                ))

        if verbose:
            for m in new_matches:
                if isinstance(m, ForwardMatch):
                    print("       AWAIT", m)
                else:
                    print("        SCAN", m)
        return new_matches

    def complete(self, cm: CompleteMatch, verbose: bool = False) \
            -> set[CMorFM]:
        """Process a new complete match."""
        if not self.cms.add(cm):
            if verbose:
                print("Duplicate:", cm)
            return set()
        if verbose:
            print("COMPLETE with", cm)

        new_matches = set()

        # For every forward match waiting where this complete match starts,
        # try to settle an open expectation or feed the new complete match
        # to the old forward match.
        for fm in self.fms.select(cm.start, cm.external):
            try:
                if len(fm.awaited) == 0:
                    new_matches.add(settle(fm, cm))
                else:
                    new_matches.add(feed(fm, cm))
            except AssertionError:
                pass
            except CyclicMatchError:
                if verbose:
                    print("    NOT upcycling", fm, cm)

        if verbose:
            for m in new_matches:
                if isinstance(m, ForwardMatch):
                    print("       AWAIT", m)
                else:
                    print("         NEW", m)
        return new_matches
