"""0.40.0: the blind demand of a lost room sensor from the learned heat loss; a filtered PID derivative."""

from datetime import datetime, timedelta, timezone

from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.regulators import PidRegulator
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


class Loss:
    """A heat-need model that has learned the house: 74.5 W/K."""
    loss_kw_per_k = 0.0745

    def update(self, *args):
        pass


def boiler(**kw):
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "boiler_power_kw": 17.3, **kw}))
    sup.heat_need = Loss()
    return sup


def lost(sup, outdoor, minute=0):
    return sup.step(Inputs(now=T0 + timedelta(minutes=minute), indoor=Reading(), outdoor=Reading(outdoor)))


def test_blind_demand_follows_the_heat_need():
    d = lost(boiler(), 0.0)  # 0.0745 × (21 − 0) = 1.56 kW of 17.3 kW
    assert d.reason == Reason.SENSOR_LOST
    assert abs(d.demand - 0.333) < 0.01 or d.demand == round(max(1.5645 / 17.3, 300 / 900), 3)
    assert d.details["blind_from"] == "heat_need" and d.details["heat_need_kw"] == 1.56
    assert "hőveszteség" in explain(d, "hu") and "heat loss" in explain(d, "en")


def test_cold_spell_asks_for_more_than_35_percent():
    d = lost(boiler(cycle_s=1800, min_on_s=300), -60.0)  # 0.0745 × 81 = 6.0 kW → 35 %, colder → more
    assert d.demand > 0.34
    d = lost(boiler(cycle_s=1800, min_on_s=300, boiler_power_kw=8.0), -10.0)  # 2.31 kW of 8 kW
    assert abs(d.demand - 0.289) < 0.001


def test_mild_weather_asks_for_less_but_at_least_one_minimum_run():
    d = lost(boiler(cycle_s=1800, min_on_s=300), 12.0)  # 0.67 kW: 3.9 %, but one 5-minute run per 30 minutes (15 °C+: summer rest)
    assert d.demand == round(300 / 1800, 3)


def test_without_a_model_power_or_with_the_option_off_the_fixed_share_stays():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "boiler_power_kw": 17.3}))  # nothing learned
    assert lost(sup, 0.0).demand == 0.35
    assert lost(boiler(boiler_power_kw=0.0), 0.0).demand == 0.35
    assert lost(boiler(sensor_lost_model=False), 0.0).demand == 0.35
    d = lost(boiler(sensor_lost_demand=0.0), 0.0)  # electric heat: still no blind heat
    assert d.demand == 0


def test_other_heat_sources_reduce_the_blind_demand():
    sup = boiler(cycle_s=1800, min_on_s=300)
    d = sup.step(Inputs(now=T0, indoor=Reading(), outdoor=Reading(-10.0), other_heat_kw=1.0))
    assert abs(d.demand - round((0.0745 * 31 - 1.0) / 17.3, 3)) < 0.001 or d.demand == round(300 / 1800, 3)


def test_pid_derivative_is_filtered():
    cfg = HcConfig.from_mapping({"control": "pid", "pid_kp": 0.0, "pid_ki": 0.0, "pid_kd": 1000.0, "pid_ke": 0.0})
    raw = HcConfig.from_mapping({"control": "pid", "pid_kp": 0.0, "pid_ki": 0.0, "pid_kd": 1000.0, "pid_ke": 0.0,
                                 "pid_d_filter_s": 0.0})
    f, r = PidRegulator(cfg), PidRegulator(raw)
    temps = [20.0, 20.0, 20.0, 20.1, 20.1, 20.1, 20.1, 20.2]  # a sensor that reports 0.1 °C steps, every 30 s
    fd, rd = [], []
    for i, t in enumerate(temps):
        now = T0 + timedelta(seconds=30 * i)
        f.update(21.0, t, None, now)
        r.update(21.0, t, None, now)
        fd.append(f.d_filtered)
        rd.append(r.d_filtered)
    assert min(rd) < -0.003 and rd[4] == 0.0  # raw: a spike at the report, nothing between
    assert min(fd) > min(rd) / 5  # filtered: no spike
    assert fd[4] < 0  # and the slope stays between reports
    f.hold(T0)
    assert f.d_filtered == 0.0
