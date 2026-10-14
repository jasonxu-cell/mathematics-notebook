"""BernoulliB with Wolfram's sign convention for B_1.

SymPy >= 1.12 switched ``bernoulli(1)`` to the ``B_1^+ = +1/2`` convention;
Mathematica has always returned ``BernoulliB[1] == -1/2`` (``B_1^-``).  Every
other Bernoulli number agrees (odd n >= 3 are zero), and the Bernoulli
polynomials ``BernoulliB[n, x]`` are unaffected, so only the single-argument
n == 1 case is overridden.  The native builtin is kept for everything else.
"""

from __future__ import annotations

from mathics.builtin.intfns.recurrence import BernoulliB


class BernoulliBWolframConvention(BernoulliB):
    name = "BernoulliB"
    context = "System`"

    rules = {
        "BernoulliB[1]": "-1/2",
    }


def register_bernoulli(session):
    BernoulliBWolframConvention(expression=False).contribute(session.definitions)
    session.definitions.clear_cache("System`BernoulliB")
