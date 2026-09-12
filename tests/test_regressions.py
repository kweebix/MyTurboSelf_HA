"""Regression tests using Home Assistant's real helpers and synthetic portal data."""
from datetime import datetime, date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from homeassistant.util import dt as dt_util
from homeassistant.helpers import config_validation as cv
from homeassistant.components.homeassistant.triggers import numeric_state
from homeassistant.components.template import trigger as template
from homeassistant.util import yaml as loader

from custom_components.myturboself.api import (
    AccountSnapshot, MyTurboSelfAuthError, MyTurboSelfApiError, TurboSelfPortalClient,
)
from custom_components.myturboself import sensor
from custom_components.myturboself.config_flow import _finite_price, _meal_selection


def snapshot(balance=10, price=1.67, meals=6, consumed=0):
    return AccountSnapshot('test', balance, price, meals, {}, None, consumed)


def entry(**options):
    return SimpleNamespace(options={'skip_holidays': False, 'skip_vacation': False, **options})


@pytest.mark.parametrize('amount,expected', [('-12,50', -12.5), ('−12,50', -12.5), ('1 234,56', 1234.56), ('0,00', 0)])
def test_signed_balance(amount, expected):
    assert TurboSelfPortalClient._parse_credits(f'<div>{amount} €</div><div>Soit : 0 repas</div>')[0] == expected


def test_unrelated_decimal_is_not_meal_count():
    assert TurboSelfPortalClient._parse_credits('<div>10,00 €</div><div>Tarif 4,50 €</div>')[1] is None


def test_portal_meals_are_authoritative():
    assert sensor._computed_meals_left(snapshot(), entry()) == 6


def test_manual_price_uses_decimal_arithmetic():
    assert sensor._computed_meals_left(snapshot(balance=0.3), entry(manual_meal_price=0.1)) == 3
    assert sensor._computed_meals_left(snapshot(balance=-0.3), entry(manual_meal_price=0.1)) == -3


def test_consumed_meal_not_counted_twice(monkeypatch):
    monkeypatch.setattr(dt_util, 'now', lambda: datetime(2026, 9, 14, 18))
    assert sensor._coverage(snapshot(meals=1, consumed=1), entry()) == (1, date(2026, 9, 16))
    assert sensor._coverage(snapshot(meals=1, consumed=0), entry()) == (1, date(2026, 9, 15))


def test_zero_balance_has_next_service_date(monkeypatch):
    monkeypatch.setattr(dt_util, 'now', lambda: datetime(2026, 9, 12, 18))
    assert sensor._coverage(snapshot(meals=0), entry()) == (0, date(2026, 9, 14))
    assert sensor._coverage(snapshot(meals=None, price=None), entry()) == (None, None)


def test_vacation_skipped(monkeypatch):
    monkeypatch.setattr(dt_util, 'now', lambda: datetime(2026, 10, 26, 8))
    assert sensor._coverage(snapshot(meals=0), entry(skip_vacation=True))[1] == date(2026, 11, 2)


def test_event_parsing():
    html = '''<tr class="rowHistoStyle"><td>14/09/2026 - 12:15</td><td>Repas midi<span>-4,60 €</span></td></tr>
    <tr class="rowHistoStyle"><td>13/09/2026 - 09:00</td><td>Rechargement<span>20,00 €</span></td></tr>'''
    events = TurboSelfPortalClient._parse_events(html)
    assert len(events) == 2
    assert events[0].is_consumption
    assert not events[1].is_consumption
    assert TurboSelfPortalClient._parse_latest_event(html) == events[0]


@pytest.mark.asyncio
async def test_expired_session():
    client = TurboSelfPortalClient('test', 'test')
    client._request = AsyncMock(return_value=('ctl00$cntForm$txtLogin', 'https://example.com/Connexion.aspx?return=1'))
    with pytest.raises(MyTurboSelfAuthError):
        await client._get_page(None, 'Accueil')


@pytest.mark.asyncio
async def test_timeout_is_connection_error():
    client = TurboSelfPortalClient('test', 'test')
    client._login = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(MyTurboSelfApiError):
        await client.async_fetch_snapshot()


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_price_rejected(value):
    with pytest.raises(vol.Invalid):
        _finite_price(value)


def test_legacy_schedule():
    assert _meal_selection(1) == ['lunch']
    assert len(_meal_selection(3)) == 3


@pytest.mark.parametrize('balance', ['', None, 'sensor.balance'])
def test_blueprint_optional_balance(balance):
    config = loader.load_yaml('blueprints/automation/myturboself_low_balance.yaml')
    config = loader.substitute(config, {'meals_sensor': 'sensor.meals', 'balance_sensor': balance, 'threshold': 3, 'notify_service': 'notify.notify', 'actions': []})
    numeric_state._TRIGGER_SCHEMA(config['trigger'][0])
    template.TRIGGER_SCHEMA(config['trigger'][1])
    cv.SCRIPT_SCHEMA(config['action'])


def test_unknown_vacation_year_does_not_crash(monkeypatch):
    monkeypatch.setattr(dt_util, 'now', lambda: datetime(2028, 1, 3, 8))
    assert sensor._coverage(snapshot(), entry(skip_vacation=True)) == (None, None)


@pytest.mark.asyncio
async def test_snapshot_counts_only_todays_consumptions(monkeypatch):
    monkeypatch.setattr(dt_util, 'now', lambda: datetime(2026, 9, 14, 18))
    client = TurboSelfPortalClient('test', 'test')
    client._login = AsyncMock()
    client._get_page = AsyncMock(side_effect=[
        '<div>10,00 €</div><div>Soit : 6 repas</div>',
        '<tr class="rowHistoStyle"><td>14/09/2026 - 12:15</td><td>Repas midi<span>-4,60</span></td></tr>'
        '<tr class="rowHistoStyle"><td>13/09/2026 - 12:15</td><td>Repas midi<span>-4,60</span></td></tr>',
    ])
    data = await client.async_fetch_snapshot()
    assert data.consumptions_today == 1
    assert data.balance == 10
    assert data.remote_meals_left == 6


def test_default_schedule_polling(monkeypatch):
    from custom_components.myturboself.coordinator import MyTurboSelfDataUpdateCoordinator
    from datetime import timedelta
    monkeypatch.setattr(dt_util, 'now', lambda: datetime(2026, 9, 14, 12))
    coordinator = object.__new__(MyTurboSelfDataUpdateCoordinator)
    coordinator.config_entry = entry()
    assert coordinator._calculate_next_interval() == timedelta(minutes=15)
