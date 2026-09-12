"""API wrapper used by the Home Assistant MyTurboSelf integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import re

import aiohttp

from homeassistant.util import dt as dt_util

from .const import DEFAULT_BASE_URL

class MyTurboSelfApiError(Exception):
    """Base exception for MyTurboSelf API failures."""


class MyTurboSelfAuthError(MyTurboSelfApiError):
    """Raised when TurboSelf rejects the provided credentials."""


@dataclass(slots=True, frozen=True)
class AccountEvent:
    """A single account event."""

    name: str
    date: datetime
    value: float
    is_consumption: bool = False


@dataclass(slots=True, frozen=True)
class AccountSnapshot:
    """Normalized TurboSelf account data."""

    source: str
    balance: float
    meal_price: float | None
    remote_meals_left: int | None
    user_data: dict[str, str]
    latest_event: AccountEvent | None
    consumptions_today: int = 0


LOGIN_USERNAME_FIELD = "ctl00$cntForm$txtLogin"
LOGIN_PASSWORD_FIELD = "ctl00$cntForm$txtMotDePasse"
TIMEOUT = 20

HOME_DATA_RE = re.compile(r'name=\"(.*?)\".*?value=\"(.*?)\"', re.DOTALL).findall
MONEY_RE = re.compile(r"[+−-]?\s*(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+),\d{2}(?!\d)")
MEALS_RE = re.compile(r"Soit\s*:\s*([+−-]?\d+)\s*repas", re.IGNORECASE)
USER_DATA_RE = re.compile(
    r'id=\"ctl00_cntForm_UC_HeaderTop_lbl(.*?)_Smartphone\"[^>]*>(.*?)<',
    re.DOTALL,
)
HISTORY_ROW_RE = re.compile(
    r'<tr[^>]*class=\"rowHistoStyle\"[^>]*>(.*?)</tr>',
    re.DOTALL,
)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
INPUT_RE = re.compile(r"<input\b([^>]+)/?>", re.IGNORECASE)
INPUT_ATTR_RE = re.compile(r'([A-Za-z_:][A-Za-z0-9_:\-]*)=\"(.*?)\"', re.DOTALL)


class TurboSelfPortalClient:
    """TurboSelf HTML client embedded in the custom integration."""

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Store credentials."""

        self._username = username.strip()
        self._password = password
        self._base_url = base_url.rstrip("/") + "/"

    async def async_fetch_snapshot(self) -> AccountSnapshot:
        """Fetch the current TurboSelf account state."""

        if not self._username or not self._password:
            raise MyTurboSelfAuthError("TurboSelf credentials are not configured")

        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                await self._login(session)
                credits_page = await self._get_page(session, "CrediterCompte")
                home_page = await self._get_page(session, "Accueil")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MyTurboSelfApiError("TurboSelf is unreachable") from err

        balance, meals_left, meal_price = self._parse_credits(credits_page)
        user_data = self._parse_user_data(home_page)
        events = self._parse_events(home_page)
        latest_event = max(events, key=lambda event: event.date, default=None)
        today = dt_util.now().date()

        return AccountSnapshot(
            source="turboself_direct",
            balance=balance,
            meal_price=meal_price,
            remote_meals_left=meals_left,
            user_data=user_data,
            latest_event=latest_event,
            consumptions_today=sum(
                event.is_consumption and event.date.date() == today
                for event in events
            ),
        )

    async def _login(self, session: aiohttp.ClientSession) -> None:
        """Log in to TurboSelf."""

        homepage, _ = await self._request(session, "GET", "Connexion.aspx")

        payload = _extract_inputs(homepage)
        if not payload:
            payload = {name: value for name, value in HOME_DATA_RE(homepage)}

        payload[LOGIN_USERNAME_FIELD] = self._username
        payload[LOGIN_PASSWORD_FIELD] = self._password
        payload.setdefault("ctl00$cntForm$ssoUser", "")
        payload["ctl00$cntForm$btnConnexion"] = "Connexion"

        response, _ = await self._request(
            session,
            "POST",
            "Connexion.aspx",
            data=payload,
            referer=self._base_url + "Connexion.aspx",
        )

        if self._looks_like_login_page(response):
            raise MyTurboSelfAuthError("TurboSelf rejected the credentials")

    async def _get_page(self, session: aiohttp.ClientSession, page_name: str) -> str:
        """Fetch an authenticated TurboSelf page."""

        response, _ = await self._request(
            session,
            "GET",
            page_name + ".aspx",
        )
        if self._looks_like_login_page(response):
            raise MyTurboSelfAuthError("TurboSelf session expired")
        return response

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> tuple[str, str]:
        """Run an HTTP request and return the HTML body and final URL."""

        headers = {}
        if referer:
            headers["Referer"] = referer

        async with session.request(
            method,
            self._base_url + path,
            data=data,
            headers=headers,
        ) as response:
            response.raise_for_status()
            return await response.text(), str(response.url)

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        """Return whether the response still looks like the login page."""

        return LOGIN_USERNAME_FIELD in html

    @staticmethod
    def _parse_credits(html: str) -> tuple[float, int | None, float | None]:
        """Parse balance, meals left and meal price."""

        text = _strip_tags(html)
        balance_match = MONEY_RE.search(text)
        if balance_match is None:
            raise MyTurboSelfApiError("Could not parse the account balance")
        balance = _parse_amount(balance_match.group())
        meals_match = MEALS_RE.search(text)
        meals_left = (
            int(meals_match.group(1).replace("−", "-")) if meals_match else None
        )
        # This ratio is an estimate: the portal's meal count may be truncated.
        meal_price = None
        if balance > 0 and meals_left and meals_left > 0:
            meal_price = round(balance / meals_left, 2)
        return balance, meals_left, meal_price

    @staticmethod
    def _parse_user_data(page_html: str) -> dict[str, str]:
        """Parse user metadata from the account page."""

        data: dict[str, str] = {}
        for key, raw_value in USER_DATA_RE.findall(page_html):
            value = _strip_tags(raw_value)
            if value:
                data[key] = value

        return data

    @staticmethod
    def _parse_latest_event(page_html: str) -> AccountEvent | None:
        """Parse the latest account event."""

        events = TurboSelfPortalClient._parse_events(page_html)
        return max(events, key=lambda event: event.date, default=None)

    @staticmethod
    def _parse_events(page_html: str) -> list[AccountEvent]:
        """Read dated events and identify explicitly labelled meal debits."""
        events = []
        for row in HISTORY_ROW_RE.findall(page_html):
            columns = TD_RE.findall(row)
            if len(columns) < 2:
                continue
            value_match = re.search(r"<span[^>]*>(.*?)</span>", columns[1], re.DOTALL)
            if value_match is None:
                continue
            raw_value = _strip_tags(value_match.group(1))
            raw_name = _strip_tags(re.sub(
                r"<span[^>]*>.*?</span>", "", columns[1], flags=re.DOTALL
            ))
            try:
                event_date = datetime.strptime(_strip_tags(columns[0]), "%d/%m/%Y - %H:%M")
                amount_match = MONEY_RE.search(raw_value)
                numeric_value = _parse_amount(amount_match.group() if amount_match else raw_value)
            except ValueError:
                continue
            is_consumption = numeric_value < 0 and any(
                word in raw_name.casefold() for word in ("repas", "consommation", "passage")
            )
            events.append(AccountEvent(raw_name, event_date, numeric_value, is_consumption))
        return events


def _parse_amount(value: str) -> float:
    """Normalize French decimal amounts, including signed grouped values."""
    return float("".join(value.split()).replace("−", "-").replace(",", "."))


def _strip_tags(value: str) -> str:
    """Remove HTML tags and normalize whitespace."""

    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return " ".join(text.split())


def _extract_inputs(page_html: str) -> dict[str, str]:
    """Extract named input values from the login form."""

    payload: dict[str, str] = {}

    for raw_attrs in INPUT_RE.findall(page_html):
        attrs = {
            key.lower(): html.unescape(value)
            for key, value in INPUT_ATTR_RE.findall(raw_attrs)
        }
        name = attrs.get("name")
        if not name:
            continue
        payload[name] = attrs.get("value", "")

    return payload
