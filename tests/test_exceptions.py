"""
Testing the exception framework
"""
import pandas as pd
from riskunwind.config import Limits
from riskunwind.exceptions import (Action, DetectorError, LimitBreach, Pipeline, RegimeChange, Response,
                                   SectorBreach, SingleNameBreach, VarBreach)

# Decision of what type of tests to create were done in conjunction/consultation with Claude.
DAY = pd.Timestamp("2020-03-16")

def repair(exc):
    return Response(exc, Action.REPAIR, trades=pd.Series({1: -100}))

def test_exact_handler_is_used():
    p = Pipeline()
    p.register(SingleNameBreach, repair)
    r = p.handle(SingleNameBreach(DAY, 0.07, 0.05, "AAPL"))
    assert r.action is Action.REPAIR
    assert r.trades[1] == -100

def test_subclass_falls_back_to_parent_handler():
    p = Pipeline()
    p.register(LimitBreach, repair)
    assert p.handle(SectorBreach(DAY, 0.3, 0.25)).action is Action.REPAIR

def test_most_specific_handler_wins():
    p = Pipeline()
    p.register(LimitBreach, repair)

    @p.register(SectorBreach)
    def tighten(exc):
        return Response(exc, Action.TIGHTEN, limits=Limits(sector=0.20))

    assert p.handle(SectorBreach(DAY, 0.3, 0.25)).action is Action.TIGHTEN
    assert p.handle(VarBreach(DAY, 0.04, 0.03)).action is Action.REPAIR

def test_no_handler_escalates():
    r = Pipeline().handle(RegimeChange(DAY, subject="calm -> dangerous"))
    assert r.action is Action.ESCALATE
    assert r.reason == "no handler"

def test_failing_handler_escalates():
    p = Pipeline()
    p.register(VarBreach, lambda exc: 1 / 0)
    p.register(SectorBreach, lambda exc: None)
    assert "ZeroDivisionError" in p.handle(VarBreach(DAY, 0.04, 0.03)).reason
    assert p.handle(SectorBreach(DAY, 0.3, 0.25)).action is Action.ESCALATE

def test_run_collects_from_every_detector():
    def yields(day):
        yield SingleNameBreach(day, 0.07, 0.05, "AAPL")
        yield SectorBreach(day, 0.3, 0.25, "Semiconductors")

    def raises(day):
        raise VarBreach(day, 0.04, 0.03)

    def crashes(day):
        raise KeyError("missing column")

    p = Pipeline()
    p.register(LimitBreach, repair)
    responses = p.run([yields, raises, crashes], DAY)
    assert [type(r.exc) for r in responses] == [SingleNameBreach, SectorBreach, VarBreach, DetectorError]
    assert [r.action for r in responses] == [Action.REPAIR] * 3 + [Action.ESCALATE]
    assert "crashes" in responses[-1].exc.subject

def test_exception_message():
    assert str(SectorBreach(DAY, 0.3, 0.25, "Semiconductors")) == \
        "SectorBreach on 2020-03-16 (Semiconductors): 0.3 vs limit 0.25"
    assert str(RegimeChange(DAY, subject="calm -> volatile")) == "RegimeChange on 2020-03-16 (calm -> volatile)"
