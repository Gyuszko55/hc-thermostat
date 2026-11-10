"""Stage 4 (EXPERIMENTAL): heating curve with room correction, against a simulated modulating heat source."""

from dataclasses import dataclass
from datetime import timedelta

from core.curve import CurveRegulator
from core.matrix import curve_supported, default_curve
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor
from sim import START

STEP = 30.0


@dataclass
class FlowHouse:
    """Room + radiators fed with a flow temperature (kW, °C, hours)."""
    indoor: float = 20.0
    outdoor: float = 0.0
    radiator: float = 20.0
    ua: float = 0.0745  # kW/K heat loss (our house)
    capacity: float = 5.36  # kWh/K (72 h time constant)
    k_rad: float = 0.0575  # kW/K radiator output per K above the room
    tau_rad_s: float = 600.0

    def advance(self, flow: float | None, dt: float = STEP) -> None:
        aim = flow if flow is not None else self.indoor
        tau = self.tau_rad_s if flow is not None else 1800.0
        self.radiator += (aim - self.radiator) * dt / tau
        q = max(self.radiator - self.indoor, 0.0) * self.k_rad
        self.indoor += (q - self.ua * (self.indoor - self.outdoor)) * (dt / 3600) / self.capacity


def run(cfg, house, hours):
    sup = Supervisor(cfg)
    now = START
    out = []
    for _ in range(int(hours * 3600 / STEP)):
        d = sup.step(Inputs(now=now, indoor=Reading(house.indoor), outdoor=Reading(house.outdoor)))
        house.advance(d.flow_setpoint if d.output else None)
        out.append(d)
        now += timedelta(seconds=STEP)
    return out


CFG = HcConfig(control="curve", target_home=22.0, night_start="00:00", night_end="00:00", season_enabled=False)


def test_curve_formula():
    cfg = HcConfig(control="curve", curve_slope=1.4, curve_shift=0.0)
    assert CurveRegulator(cfg).base(22.0, 2.0) == 22.0 + 1.4 * 20


def test_holds_the_target_at_several_outdoor_temperatures():
    for outdoor in (8.0, 0.0, -10.0):
        decisions = run(CFG, FlowHouse(indoor=21.0, outdoor=outdoor), hours=48)
        temps = [d.indoor for d in decisions[-2880:]]
        assert min(temps) > 21.5 and max(temps) < 22.5, (outdoor, min(temps), max(temps))


def test_room_correction_fixes_a_wrong_curve():
    cfg = HcConfig(**{**CFG.__dict__, "curve_slope": 1.0})  # too flat for this house
    temps = [d.indoor for d in run(cfg, FlowHouse(indoor=21.0, outdoor=-5.0), hours=72)[-2880:]]
    assert abs(sum(temps) / len(temps) - 22.0) < 0.3


def test_no_heat_when_it_is_mild_outside():
    decisions = run(CFG, FlowHouse(indoor=22.5, outdoor=21.0), hours=2)
    assert not any(d.output for d in decisions[10:])


def test_boost_asks_for_the_highest_flow():
    cfg = HcConfig(**{**CFG.__dict__, "boost_enabled": True})
    d = run(cfg, FlowHouse(indoor=20.0, outdoor=0.0), hours=0.05)[0]
    assert d.reason == Reason.BOOST and d.flow_setpoint == cfg.flow_max


def test_heat_pump_runs_long_and_pauses_long():
    cfg = HcConfig(**{**CFG.__dict__, **default_curve("radiator_single", "heat_pump")})
    decisions = run(cfg, FlowHouse(indoor=21.8, outdoor=21.0), hours=24)  # almost no heat need: it must cycle
    spans, current, state = [], 0, decisions[0].output
    for d in decisions:
        if d.output == state:
            current += 1
        else:
            spans.append((state, current * STEP / 60))
            state, current = d.output, 1
    closed = spans[1:]  # the first span may have started before the run
    assert any(on for on, _ in closed), "it should cycle in mild weather"
    assert all(minutes >= 20 for on, minutes in closed if on)
    assert all(minutes >= 10 for on, minutes in closed if not on)


def test_heat_pump_runs_continuously_when_it_is_cold():
    cfg = HcConfig(**{**CFG.__dict__, **default_curve("radiator_single", "heat_pump")})
    decisions = run(cfg, FlowHouse(indoor=22.0, outdoor=0.0), hours=12)
    assert all(d.output for d in decisions[-1440:])


def test_text_names_the_flow():
    d = run(CFG, FlowHouse(indoor=21.5, outdoor=0.0), hours=0.5)[-1]
    assert d.flow_setpoint is not None and "Előremenő" in explain(d, "hu")


def test_only_for_modulating_sources():
    assert curve_supported("modulating_boiler") and curve_supported("heat_pump")
    assert not curve_supported("onoff_boiler")
    assert default_curve("floor_single", "modulating_boiler")["flow_max"] == 45.0
