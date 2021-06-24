"""Interactions between forwards and complete match."""

from typing import Literal, Sequence

from matches import ForwardMatch, CompleteMatch


def settle(fm: "ForwardMatch", cm: "CompleteMatch") -> "CompleteMatch":
    """Create a complete match satisfying a forward match's expectation."""

    # fm has all its required children
    assert len(fm.awaited) == 0

    # cm satisfies fm's expectation and they can concatenate
    assert fm.expectation(cm.external)
    assert can_concat(fm.last, cm)

    return CompleteMatch(
        rule=fm.rule,
        start=fm.start,
        close=fm.close,
        name=fm.name,
        children=fm.children,
        lbro=fm.lbro,
        rbro=cm,
    )


def feed(fm: "ForwardMatch", cm: "CompleteMatch"):
    """Advance, and eventually complete, a forward match."""

    # cm is actually awaited
    assert len(fm.awaited) != 0
    assert fm.awaited[0] == cm.external
    assert fm.close == cm.start

    # The new match still needs fm's left-brother as context on the left
    left_brother = fm.lbro

    if len(fm.children) > 0:
        # fm last child and cm must concatenate
        assert can_concat(fm.last, cm)

    else:
        if fm.upon is not None:
            # cm must be built on top of fm.upon, if present
            assert fm.upon in history_at_start(cm)

        if left_brother is not None:
            # there is no child, but fm's left context and cm must concatenate
            assert can_concat(left_brother, cm)

        else:
            # if fm needs no context on the left, the new match will
            # inherit cm's left brother, if present
            left_brother = cm.lbro

    fmatch = ForwardMatch(
        rule=fm.rule,
        start=fm.start,
        close=cm.close,
        name=fm.name,
        children=(*fm.children, cm),
        lbro=left_brother,
        upon=fm.upon,
    )
    try:
        # Try to see if the new forward match is already complete.
        newcm = CompleteMatch.from_forward(fmatch)

        # If a grammar as rules like 〈 A → B 〉, 〈 B → C 〉, 〈 C → A 〉, the
        # parser must not generate an infinite wrapping cycle.
        prev = next((m for m in cm.wrapping_history()
                     if m.external == newcm.external), None)

        # If no previous match has the same external, it is not a wrapping
        # cycle, it is acceptable.
        if prev is None:
            return newcm

        # If there is a previous match with the same external and exactly
        # the same wrapping span of the new one, it is considered a cyclic
        # match and rejected.
        if (wrapping_span(newcm, side="both") 
                == wrapping_span(prev, side="both")):
            raise CyclicMatchError

        # In some edge case, the previous match and the new one are
        # repetition of the same wrapping cycle but their sides (
        # left-brother or right-brother) are different. Extra care is needed
        # to separate useful and useless wrapping cycles.
        if (wrapping_span(newcm, side="none") 
                == wrapping_span(prev, side="none")):

            # left side is new if...
            new_on_left = (
                # newcm have a left-brother and prev do not or...
                (prev.lbro is None and newcm.lbro is not None)
                or (
                    # newcm's left-brother is different and can't be used as
                    # left-brother for prev.
                    prev.lbro is not None
                    and wrapping_span(prev, side="left")
                        != wrapping_span(newcm, side="left")
                    and not can_concat(newcm.lbro, prev)
                )
            )

            # right side is new if...
            new_on_right = (
                # newcm has a right-brother and prev do not or...
                (prev.rbro is None and newcm.rbro is not None)
                or (
                    # newcm's right-brother is different and can't be used as
                    # right-brother for prev.
                    prev.rbro is not None
                    and wrapping_span(prev, side="right")
                        != wrapping_span(newcm, side="right")
                    and not can_concat(prev, newcm.rbro)
                )
            )

            if not new_on_left and not new_on_right:
                raise CyclicMatchError

        # If no CyclicMatchError was raised, it is a legitimate complete match.
        return newcm

    except AssertionError:
        # Trying to complete the match gave an error, so it is still a
        # forward match.
        return fmatch


def can_concat(left: "CompleteMatch", right: "CompleteMatch") -> bool:
    """Determine if left and right match can concatenate."""

    # The request of left is what it needs as right context
    # The request of right is what it needs as left context
    left_req = left.rbro
    right_req = right.lbro

    # Not only the match itself is considered, but its entire history; left
    # match closes where right match starts.
    left_history = history_at_close(left)
    right_history = history_at_start(right)

    if left_req is None and right_req is None:
        # No context is needed
        return True

    elif left_req is None:
        # left needs no context
        return right_req in left_history

    elif right_req is None:
        # right needs no context
        return left_req in right_history

    elif left_req in right_history and right_req in left_history:
        # Both matches need context: they shall not cross
        # Indexes in histories are from the newest at index 0 to the oldest.

        # Index of the oldest (i.e. the first) match in left's history that
        # needs left_req as context.
        left_oldest = max((i for i, lm in enumerate(left_history)
                           if lm.rbro == left_req))

        # Index of the match in left's history that is required by right
        left_needed = left_history.index(right_req)

        # Index of the oldest (i.e. the first) match in right's history that
        # needs right_req as context.
        right_oldest = max((i for i, rm in enumerate(right_history)
                            if rm.lbro == right_req))

        # Index of the match in right's history that is required by left
        right_needed = right_history.index(left_req)

        if left_oldest < left_needed:
            # In this case the match at left_needed is to be constructed
            # before the match at left_oldest. Therefore the match at
            # right_oldest (which really needs left_needed) shall be
            # constructable before the match at right_needed (which is needed
            # by left_oldest). They can be the same match.
            return right_needed <= right_oldest
        else:
            # In this case the match at left_needed is to be constructed
            # after the match at left_oldest or they are the same match.
            # Therefore the match at right_oldest (which really needs
            # left_needed) must be constructed after the match at
            # right_needed (which is needed by left_oldest). They can be the
            # same match.
            return right_oldest < right_needed
    else:
        # One of the requests is not in other's history
        return False


def wrapping_span(cm: CompleteMatch,
                  side: Literal["left", "right", "both", "none"] = "none") \
        -> Sequence[set[str]]:
    """Sets of the externals used in wrapping cycles by cm and its context.

    Args:
        cm: a complete match
        side: indicates which context is required, left, right, both or none.
    """
    central_wrappings = {m.external for m in cm.wrapping_history()},
    if cm.lbro is None or side == "right":
        left_wrappings = tuple()
    else:
        left_wrappings = wrapping_span(cm.lbro, side="left")
    if cm.rbro is None or side == "left":
        right_wrappings = tuple()
    else:
        right_wrappings = wrapping_span(cm.rbro, side="right")
    if side == "none":
        return central_wrappings
    else:
        return left_wrappings + central_wrappings + right_wrappings


class CyclicMatchError(Exception):
    """Exception when a match would be a useless renaming of itself."""


def history_at_start(match: "CompleteMatch"):
    """All the matches inside given match with the same starting position.

    The sequence goes from newest (match itself) to oldest (a terminal).
    """
    if len(match.children) == 0:
        return match,
    else:
        return match, *history_at_start(match.first)


def history_at_close(match: "CompleteMatch"):
    """All the matches inside given match with the same closing position.

    The sequence goes from newest (match itself) to oldest (a terminal).
    """
    if len(match.children) == 0:
        return match,
    else:
        return match, *history_at_close(match.last)
