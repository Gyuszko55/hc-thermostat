"""0.78.5: the AI analysis of an active house covers only the instances that control (not shadow members), and only
their own open issues plus the house-wide ones."""

from types import SimpleNamespace

from custom_components.hc_thermostat import ai_report as A


def _e(eid, mode, title=None):
    return SimpleNamespace(entry_id=eid, data={}, options={"mode": mode}, title=title or eid, runtime_data=object())


class _Entries:
    def __init__(self, entries):
        self._e = {e.entry_id: e for e in entries}

    def async_get_entry(self, i):
        return self._e.get(i)

    def async_entries(self, domain):
        return list(self._e.values())


def _hass(entries, monkeypatch, host, members):
    import custom_components.hc_thermostat.info as info
    monkeypatch.setattr(info, "house_links", lambda hass: {host: SimpleNamespace(host=host, members=members)})
    return SimpleNamespace(config_entries=_Entries(entries))


def test_active_host_keeps_only_active_members(monkeypatch):
    e = [_e("boiler", "active"), _e("klima", "active"), _e("olaj", "shadow")]
    h = _hass(e, monkeypatch, "boiler", ["boiler", "klima", "olaj"])
    assert [x.entry_id for x in A.house_entries(h, "boiler")] == ["boiler", "klima"]


def test_shadow_host_keeps_everyone(monkeypatch):
    e = [_e("psz", "shadow"), _e("puffer", "shadow"), _e("hp", "active")]
    h = _hass(e, monkeypatch, "psz", ["psz", "puffer", "hp"])
    assert [x.entry_id for x in A.house_entries(h, "psz")] == ["psz", "puffer", "hp"]


def test_issues_of_other_houses_left_out():
    all_ids = {"01BOILER", "01KLIMA", "01PSZRAD"}
    inc = {"01BOILER", "01KLIMA"}
    assert A._own_issue("source_problem_01BOILER", inc, all_ids)
    assert not A._own_issue("circuit_problem_01PSZRAD", inc, all_ids)
    assert A._own_issue("safety_stop", inc, all_ids)            # house-wide (no entry id): stays
