"""
General exception framework: 
1. detect 
2. handle 
3. escalate
- detectors raise typed RiskExceptions
- one handler per exception type
- no handler, a failing handler, or a crashing detector -> escalate

Assumptions:
- Handlers only propose: trades, tighter limits
- Exceptions are handled in the order detectors produce them
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable
import pandas as pd
from riskunwind.config import Limits

@dataclass(eq=False)
class RiskException(Exception):
    day: pd.Timestamp
    value: float = math.nan
    limit: float = math.nan
    subject: str = "" 

    def __str__(self) -> str:
        text = f"{type(self).__name__} on {self.day.date()}"
        if self.subject:
            text += f" ({self.subject})"
        if not math.isnan(self.limit):
            text += f": {self.value:.4g} vs limit {self.limit:.4g}"
        return text

class LimitBreach(RiskException):
    pass

class SingleNameBreach(LimitBreach):
    pass

class SectorBreach(LimitBreach):
    pass

class VarBreach(LimitBreach):
    pass

class LiquidityBreach(LimitBreach):
    pass

class ReserveBreach(LimitBreach):
    pass

class RegimeChange(RiskException):
    pass

class DetectorError(RiskException):
    pass

class Action(Enum):
    REPAIR = "repair"       # propose trades
    TIGHTEN = "tighten"     # stricter limits
    ESCALATE = "escalate"   # hand to a person

@dataclass
class Response:
    exc: RiskException
    action: Action
    reason: str = ""
    trades: pd.Series | None = None     # permno => shares to trade
    limits: Limits | None = None

Handler = Callable[[RiskException], Response]
Detector = Callable[..., Iterable[RiskException]]

def escalate(exc: RiskException, reason: str) -> Response:
    return Response(exc, Action.ESCALATE, reason)

@dataclass
class Pipeline:
    handlers: dict[type, Handler] = field(default_factory=dict)

    def register(self, exc_type: type, handler: Handler | None = None):
        """Use directly or as a decorator"""
        def add(h: Handler) -> Handler:
            self.handlers[exc_type] = h
            return h
        return add if handler is None else add(handler)

    def handler_for(self, exc: RiskException) -> Handler | None:
        """Most specific registered handler (SectorBreach before LimitBreach)"""
        for cls in type(exc).__mro__:
            if cls in self.handlers:
                return self.handlers[cls]
        return None

    def handle(self, exc: RiskException) -> Response:
        handler = self.handler_for(exc)
        if handler is None:
            return escalate(exc, "no handler")
        try:
            response = handler(exc)
        except Exception as err:
            return escalate(exc, f"handler failed: {err!r}")
        if not isinstance(response, Response):
            return escalate(exc, "handler gave no response")
        return response

    def detect(self, detectors: Iterable[Detector], *args, **kwargs) -> list[RiskException]:
        found = []
        for detector in detectors:
            try:
                found.extend(detector(*args, **kwargs))
            except RiskException as exc:
                found.append(exc)
            except Exception as err:
                name = getattr(detector, "__name__", repr(detector))
                found.append(DetectorError(pd.NaT, subject=f"{name}: {err!r}"))
        return found

    def run(self, detectors: Iterable[Detector], *args, **kwargs) -> list[Response]:
        return [self.handle(exc) for exc in self.detect(detectors, *args, **kwargs)]
