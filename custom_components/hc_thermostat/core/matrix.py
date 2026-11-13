"""Control matrix: heat source x emitter/hydraulics -> recommended control.

Engineering defaults, not an installation design. Own control in the first release
exists only for on/off relays; other sources run through an external thermostat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    RECOMMENDED = "recommended"
    POSSIBLE = "possible"
    NOT_RECOMMENDED = "not_recommended"


SOURCES = ("onoff_boiler", "modulating_boiler", "heat_pump", "electric_boiler", "air_conditioner", "electric_heater",
           "storage_heater", "district_heating", "pellet_boiler", "external_heat")
# 0.47.0: a heat source HC does not drive (a PLC, a heat pump's own controller, a boiler with its own logic): HC only
# switches the rooms' zone valves – it need not know what makes the heat
ROOM_SOURCES = ("air_conditioner", "electric_heater", "storage_heater")
ELECTRIC_SOURCES = ("electric_heater", "electric_boiler", "storage_heater")  # may run on controlled power  # units in the room itself, no water loop
SYSTEMS = (
    "radiator_single", "radiator_trv", "radiator_zones", "floor_single", "floor_zones",
    "mixed_no_circuit", "mixed_rtl", "mixed_mixing", "room_unit", "fan_coil",
)


@dataclass(frozen=True)
class Cell:
    status: Status
    text_hu: str
    text_en: str


R, P, N = Status.RECOMMENDED, Status.POSSIBLE, Status.NOT_RECOMMENDED

MATRIX: dict[tuple[str, str], Cell] = {
    ("radiator_single", "onoff_boiler"): Cell(R, "TPI vagy PID + PWM, referenciahelyiség szerint", "TPI or PID + PWM, by a reference room"),
    ("radiator_single", "modulating_boiler"): Cell(R, "Fűtési görbe + helyiségkorrekció; lehetséges: relés mód", "Heating curve + room correction; possible: relay mode"),
    ("radiator_single", "heat_pump"): Cell(R, "Görbe, hosszú futások, minimális futási idő; nem PWM", "Curve, long runs, minimum run time; no PWM"),
    ("radiator_trv", "onoff_boiler"): Cell(R, "TRV helyiségenként, a kazánt az igénylő zónák indítják; kell átfolyás", "Room TRVs, the boiler starts on zone demand; flow path required"),
    ("radiator_trv", "modulating_boiler"): Cell(R, "TRV + görbe, a legnagyobb igény emeli az előremenőt", "TRV + curve, the highest demand raises the flow"),
    ("radiator_trv", "heat_pump"): Cell(P, "TRV türelmes beállítással; minimális átfolyás vagy puffer feltétellel", "Patient TRV settings; needs minimum flow or a buffer"),
    ("radiator_zones", "onoff_boiler"): Cell(R, "Zónánként TPI, a kazán a nyitott zónáktól függ", "TPI per zone, the boiler follows open zones"),
    ("radiator_zones", "modulating_boiler"): Cell(R, "Zóna + görbe", "Zones + curve"),
    ("radiator_zones", "heat_pump"): Cell(P, "Zóna + görbe, puffer vagy minimális átfolyás feltétellel", "Zones + curve; needs a buffer or minimum flow"),
    ("floor_single", "onoff_boiler"): Cell(R, "Hosszú ciklusú TPI, a keverő fix hőfokon; padlóhőfok-limit", "Long cycle TPI, fixed mixer; floor limit"),
    ("floor_single", "modulating_boiler"): Cell(R, "Alacsony görbe, hosszú ciklus; padlóhőfok-limit", "Low curve, long cycle; floor limit"),
    ("floor_single", "heat_pump"): Cell(R, "Alacsony görbe, a padló mint hőtároló", "Low curve, the floor as heat storage"),
    ("floor_zones", "onoff_boiler"): Cell(R, "Zónánként hosszú ciklusú TPI, a szivattyú csak nyitott körrel", "Long cycle TPI per zone, pump only with an open loop"),
    ("floor_zones", "modulating_boiler"): Cell(R, "Zónák + alacsony görbe", "Zones + low curve"),
    ("floor_zones", "heat_pump"): Cell(R, "Zónák + alacsony görbe, a szelepek ne zárjanak le egyszerre", "Zones + low curve, never close all valves"),
    ("mixed_no_circuit", "onoff_boiler"): Cell(N, "Átkötés nélkül nem ajánlott; csak ha a padló méretezése engedi az előremenőt", "Not without rework; only if the floor design allows the flow temperature"),
    ("mixed_no_circuit", "modulating_boiler"): Cell(P, "A görbét a padló maximuma korlátozza, a radiátor gyengébb lesz", "The floor limit caps the curve, radiators get weaker"),
    ("mixed_no_circuit", "heat_pump"): Cell(P, "Alacsony hőfokú radiátorokkal, közös görbével", "With low temperature radiators and a shared curve"),
    ("mixed_rtl", "onoff_boiler"): Cell(P, "Radiátor főkör TPI-vel, a padlót az RTL korlátozza; kis felületre", "Radiator loop with TPI, the RTL limits the floor; small areas"),
    ("mixed_rtl", "modulating_boiler"): Cell(P, "Radiátor-görbe, az RTL marad a védelem", "Radiator curve, the RTL stays as protection"),
    ("mixed_rtl", "heat_pump"): Cell(N, "Az RTL alacsony hőfokon gyengén nyílik", "An RTL opens poorly at low temperatures"),
    ("mixed_mixing", "onoff_boiler"): Cell(R, "Két zóna, a kazán bármelyik igényére indul; a padló hosszú ciklusú, biztonsági hőfokkapcsolóval", "Two zones, boiler on either demand; long floor cycle with a safety thermostat"),
    ("mixed_mixing", "modulating_boiler"): Cell(R, "Radiátor-görbe a kazánon, a keverő külön padló-görbével", "Radiator curve on the boiler, separate floor curve on the mixer"),
    ("mixed_mixing", "heat_pump"): Cell(P, "Két kör, de az előremenő a magasabb igényhez igazodik, ami rontja a COP-ot", "Two loops, but the flow follows the higher demand, which lowers COP"),
 ("radiator_single", "electric_boiler"): Cell(R, "TPI vagy PID + PWM a mágneskapcsolón; a kazán saját termosztátja maradjon felül", "TPI or PID + PWM on the contactor; keep the boiler's own thermostat above"),
    ("radiator_trv", "electric_boiler"): Cell(R, "TRV helyiségenként, a kazánt az igénylő zónák indítják; kell átfolyás", "Room TRVs, the boiler starts on zone demand; flow path required"),
    ("radiator_zones", "electric_boiler"): Cell(R, "Zónánként TPI, a kazán a nyitott zónáktól függ", "TPI per zone, the boiler follows open zones"),
    ("floor_single", "electric_boiler"): Cell(R, "Hosszú ciklusú TPI, alacsony vízhőfok a kazánon; padlóhőfok-limit", "Long cycle TPI, low water temperature on the boiler; floor limit"),
    ("floor_zones", "electric_boiler"): Cell(R, "Zónánként hosszú ciklusú TPI, a szivattyú csak nyitott körrel", "Long cycle TPI per zone, pump only with an open loop"),
    ("mixed_no_circuit", "electric_boiler"): Cell(N, "Átkötés nélkül nem ajánlott; csak ha a padló méretezése engedi az előremenőt", "Not without rework; only if the floor design allows the flow temperature"),
    ("mixed_rtl", "electric_boiler"): Cell(P, "Radiátor főkör TPI-vel, a padlót az RTL korlátozza; kis felületre", "Radiator loop with TPI, the RTL limits the floor; small areas"),
    ("mixed_mixing", "electric_boiler"): Cell(R, "Két zóna, a kazán bármelyik igényére indul; a padló hosszú ciklusú", "Two zones, boiler on either demand; long floor cycle"),
}

_FLOOR = {"floor_single", "floor_zones"}


_AC = Cell(Status.RECOMMENDED, "Klíma: a célját a helyiséghőmérő szerint tolja el (virtuális i-Feel), nem kapcsolgatja; nyáron hűt",
           "Air conditioner: its setpoint follows the room thermometer (virtual i-Feel), never switched to regulate; cools in summer")
_HEATER = Cell(Status.RECOMMENDED, "Elektromos fűtő: relén vagy okosdugaljon TPI/PID + PWM rövid ciklussal; wifis, saját termosztátos fűtőnél külső termosztát mód",
               "Electric heater: TPI/PID + PWM with a short cycle on a relay or smart plug; for a Wi-Fi heater with its own thermostat, external thermostat mode")
_STORAGE = Cell(Status.RECOMMENDED,
                "Hőtárolós kályha: éjszakai (vezérelt áramos) feltöltés a kinti napi átlag szerint, az ablak végére időzítve; nappal kisütés ventilátorral a helyiség hőfoka szerint",
                "Storage heater: night (off-peak) charge by the outdoor daily average, timed to the end of the window; daytime discharge by a fan, by the room temperature")
_FANCOIL = Cell(Status.RECOMMENDED,
                "Fan-coil: a vízszelepet TPI/PID kapcsolja, a ventilátor fordulata az igényt követi (zárás után rövid utánfutás); "
                "hideg hőcserélőnél a ventilátor nem indul",
                "Fan coil: TPI/PID switches the water valve, the fan speed follows the demand (short overrun after closing); "
                "no fan while the coil is cold")
_DISTRICT = {
    "radiator_single": Cell(R, "Távfűtés lakásonkénti zónaszeleppel: TPI vagy PID + PWM hosszú ciklussal; visszatérő-korlát lehetséges",
                            "District heating with a flat zone valve: TPI or PID + PWM with a long cycle; return limit possible"),
    "radiator_trv": Cell(R, "Távfűtés szelepfejekkel: a fejek kapják a célt (külső termosztát mód), nincs kazán",
                         "District heating with TRV heads: the heads get the target (external thermostat), no boiler"),
    "radiator_zones": Cell(R, "Zónánként zónaszelep TPI-vel", "A zone valve per zone with TPI"),
    "floor_single": Cell(R, "Hőközpont keverővel, zónaszelep hosszú ciklussal; padlóhőfok-limit", "Substation with mixing, zone valve with a long cycle; floor limit"),
    "floor_zones": Cell(R, "Hőközpont keverővel, zónánként szelep; padlóhőfok-limit", "Substation with mixing, a valve per zone; floor limit"),
}
_DISTRICT_OTHER = Cell(P, "Távfűtés vegyes rendszeren: zónaszelep TPI-vel, a keverést a hőközpont végzi",
                       "District heating on a mixed system: zone valve with TPI, the substation mixes")
_EXTERNAL = Cell(R, "Külső vezérlésű hőtermelő: a HC csak a helyiség zónaszelepét kapcsolja (TPI vagy PID + PWM); a hőtermelőt és a "
                    "szivattyút a saját vezérlése indítja. Lassú termoszelepnél és késleltetett szivattyúnál add meg a hasznos fűtés késését.",
                 "Heat source with its own control: HC only switches the room's zone valve (TPI or PID + PWM); the heat source and "
                 "the pump are started by their own control. With a slow thermoelectric valve or a delayed pump set the useful heat delay.")
_PELLET = Cell(R, "Pellet kazán: on-off vezérlés hosszú futásokkal (legalább 45 perc, 20 perc szünet); puffertartállyal a "
                  "puffer szerep tölti, a körök zónaként fűtenek",
               "Pellet boiler: on/off with long runs (45 minutes at least, 20 minutes pause); with a buffer tank the buffer "
               "role charges it and the circuits heat as zones")
_PELLET_FLOOR = Cell(R, "Pellet kazán padlóra: puffer és keverőkör ajánlott; on-off vezérlés hosszú futásokkal, padlóhőfok-limit",
                     "Pellet boiler on a floor: a buffer and a mixing loop are advised; on/off with long runs, floor limit")
_ODD = Cell(Status.NOT_RECOMMENDED, "Ez a hőforrás nem ehhez a rendszerhez való", "This heat source does not fit this system")
_EFLOOR = Cell(Status.RECOMMENDED,
               "Elektromos padlófűtés (fűtőszőnyeg, fűtőkábel): TPI vagy PID + PWM 20–30 perces ciklussal; padlószenzor és "
               "padlóhőfok-limit kötelező (alapból 27 °C), a padlószenzor kiesésekor nem fűt",
               "Electric floor heating (heating mat or cable): TPI or PID + PWM with a 20–30 minute cycle; a floor sensor and "
               "a floor temperature limit are required (27 °C by default), no heat when the floor sensor is lost")


def floor_system(system: str | None) -> bool:
    """Floor heating, water or electric (floor tempering, floor fallback)."""
    return system in _FLOOR


def electric_floor(system: str | None, source: str | None) -> bool:
    """An electric heating mat or cable under the floor: relay control, floor limit required."""
    return source == "electric_heater" and system in _FLOOR


def cell(system: str, source: str) -> Cell:
    if electric_floor(system, source):
        return _EFLOOR
    if (system == "room_unit") != (source in ROOM_SOURCES) or (system == "fan_coil" and source in ROOM_SOURCES):
        return _ODD
    if system == "fan_coil":
        return _FANCOIL
    if source == "district_heating":
        return _DISTRICT.get(system, _DISTRICT_OTHER)
    if source == "external_heat":
        return _EXTERNAL
    if source == "pellet_boiler":
        return _PELLET_FLOOR if system in _FLOOR else _PELLET
    if source == "air_conditioner":
        return _AC
    if source == "electric_heater":
        return _HEATER
    if source == "storage_heater":
        return _STORAGE
    return MATRIX[(system, source)]


def own_control_supported(source: str) -> bool:
    """Own control (TPI/PID + PWM) switches a relay: on/off gas boiler, electric boiler, electric heater – and a
    modulating boiler on its room-thermostat contacts (relay mode; it modulates by itself while on)."""
    return source in ("onoff_boiler", "modulating_boiler", "electric_boiler", "electric_heater", "district_heating",
                      "external_heat")


def controls(source: str, system: str | None = None) -> list[str]:
    """The controls offered for a heat source, the recommended one first. A fan coil switches its own water valve
    (TPI / PID) whatever feeds it."""
    if system == "fan_coil":
        return ["tpi", "pid", "external"]
    if source == "air_conditioner":
        return ["ac", "external"]
    if source == "storage_heater":
        return ["storage"]
    if source == "pellet_boiler":
        return ["onoff", "external"]  # long runs, no PWM: it ignites and burns out slowly  # charge relay (+ discharge fan); its own thermostat stays as a backstop
    out = ["curve"] if curve_supported(source) else []
    if source == "heat_pump":
        out.append("onoff")  # on its thermostat input: long runs, no PWM
    if own_control_supported(source):
        out += ["tpi", "pid"]
    return out + ["external"]


def curve_supported(source: str) -> bool:
    """Heating curve with a flow setpoint (EXPERIMENTAL): modulating boilers and heat pumps."""
    return source in ("modulating_boiler", "heat_pump")


def default_curve(system: str, source: str) -> dict:
    """Starting curve: steeper for radiators, flat and low for floor heating."""
    floor = system in _FLOOR
    return {"curve_slope": 0.5 if floor else 1.4, "flow_max": 45.0 if floor else (55.0 if source == "heat_pump" else 75.0),
            "flow_min": 22.0 if floor else 25.0, "heat_pump": source == "heat_pump"}


def min_cycle_s(valve_delay_s: float, min_on_s: float, min_off_s: float) -> float:
    """0.48.1: the shortest cycle a run with a valve delay can give useful heat in (a shorter one gives none or
    only full cycles)."""
    return max(0.0, valve_delay_s) + max(0.0, min_on_s) + max(0.0, min_off_s)


def fit_cycle(cycle_s: float, valve_delay_s: float, min_on_s: float, min_off_s: float) -> float:
    """0.48.1: a cycle too short for its valve delay is lengthened to 1.5 × the shortest, in whole 5 minutes."""
    if valve_delay_s <= 0 or cycle_s >= min_cycle_s(valve_delay_s, min_on_s, min_off_s):
        return cycle_s
    need = 1.5 * min_cycle_s(valve_delay_s, min_on_s, min_off_s)
    return float(-(-need // 300) * 300)


def default_timing(system: str, source: str | None = None) -> dict[str, float]:
    """Editable starting values; slow floors get long cycles."""
    if electric_floor(system, source):  # a mat warms faster than a water floor, but a screed still evens out slowly
        return {"cycle_s": 1800.0, "min_on_s": 300.0, "min_off_s": 300.0}
    if system in _FLOOR:
        return {"cycle_s": 3600.0, "min_on_s": 900.0, "min_off_s": 900.0}
    if source == "pellet_boiler" and system != "fan_coil":  # ignition 10–15 min, burn-out after the stop
        return {"cycle_s": 3600.0, "min_on_s": 2700.0, "min_off_s": 1200.0}
    if system == "fan_coil":  # a motorised valve and a fan: quick, but the valve deserves some rest
        return {"cycle_s": 900.0, "min_on_s": 180.0, "min_off_s": 180.0}
    if source in ("district_heating", "external_heat") and system not in _FLOOR:  # zone valve: long, calm cycles
        return {"cycle_s": 1800.0, "min_on_s": 600.0, "min_off_s": 300.0}
    if system == "room_unit":  # an electric heater warms up in seconds; a relay or plug still deserves some rest
        return {"cycle_s": 600.0, "min_on_s": 120.0, "min_off_s": 120.0}
    return {"cycle_s": 900.0, "min_on_s": 300.0, "min_off_s": 300.0}


def source_defaults(system: str | None, source: str | None) -> dict:
    """Safety defaults that depend on the heat source; an explicit setting of the instance always wins."""
    out: dict = {}
    if source == "electric_heater":
        out["sensor_lost_demand"] = 0.0  # no indoor reading: an electric heater does not heat blind
    if electric_floor(system, source):
        out.update(floor_max=27.0, floor_required=True)
    elif system in _FLOOR:
        out["floor_max"] = 29.0  # a water floor: the usual surface limit; acts only with a floor sensor
    if system == "fan_coil":
        out["fan_coil"] = True  # the fan follows the valve's demand
    if source == "heat_pump" and system != "fan_coil":
        out["heat_pump"] = True  # long runs (hp_min_on_s / hp_min_off_s) in curve and on/off control
    return out
