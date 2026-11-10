"""0.24.0: the controller's settings and state as climate attributes, like the Smart Thermostat's."""

from datetime import datetime, timezone

from core.model import HcConfig
from core.regulators import controller_attributes
from core.supervisor import Supervisor

NIGHT = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)
DAY = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def test_pid_attributes():
    cfg = HcConfig(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2, pid_kd=0.0, target_home=22.5, target_night=21.0,
                   night_start="22:00", night_end="05:30")
    sup = Supervisor(cfg)
    sup.regulator.integral = 0.0731
    a = controller_attributes(cfg, sup, 0.27, DAY)
    assert (a["kp"], a["ki"], a["ki_unit"], a["kd"]) == (0.5, 0.2, "1/h", 0.0)
    assert a["pid_i"] == 7.31 and a["control_output"] == 27.0
    assert (a["home_temp"], a["sleep_temp"], a["night_end"]) == (22.5, 21.0, "05:30")
    assert "tpi_coef_int" not in a


def test_ki_per_second_is_shown_per_hour():
    cfg = HcConfig(control="pid", pid_ki=0.00005)
    a = controller_attributes(cfg, Supervisor(cfg), 0.0, DAY)
    assert a["ki"] == 0.18


def test_tpi_attributes():
    cfg = HcConfig(control="tpi", tpi_coef_int=0.6, tpi_coef_ext=0.01)
    a = controller_attributes(cfg, Supervisor(cfg), 0.1, DAY)
    assert a["tpi_coef_int"] == 0.6 and a["tpi_coef_ext"] == 0.01 and "kp" not in a


def test_active_preset_follows_schedule_and_set_preset():
    cfg = HcConfig(night_start="22:00", night_end="05:30")
    sup = Supervisor(cfg)
    assert sup.active_preset(DAY) == "home"
    assert sup.active_preset(NIGHT) == "sleep"
    sup.set_preset("comfort", DAY)
    assert sup.active_preset(NIGHT) == "comfort"
