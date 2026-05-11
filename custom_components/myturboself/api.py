"""API wrapper used by the Home Assistant MyTurboSelf integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import re

import aiohttp

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


@dataclass(slots=True, frozen=True)
class AccountSnapshot:
    """Normalized TurboSelf account data."""

    source: str
    balance: float
    meal_price: float | None
    remote_meals_left: int | None
    user_data: dict[str, str]
    latest_event: AccountEvent | None


LOGIN_USERNAME_FIELD = "ctl00$cntForm$txtLogin"
LOGIN_PASSWORD_FIELD = "ctl00$cntForm$txtMotDePasse"
TIMEOUT = 20

HOME_DATA_RE = re.compile(r'name=\"(.*?)\".*?value=\"(.*?)\"', re.DOTALL).findall
CREDITS_RE = re.compile(r"[>\n ]*?(\d+,\d+)|>Soit : (\d*) repas").findall
USER_DATA_RE = re.compile(
    r'id=\"ctl00_cntForm_UC_HeaderTop_lbl(.*?)_Smartphone\"[^>]*>(.*?)<',
    re.DOTALL,
)
HISTORY_ROW_RE = re.compile(
    r'<tr[^>]*class=\"rowHistoStyle\"[^>]*>(.*?)</tr>',
    re.DOTALL,
)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)


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
        except aiohttp.ClientError as err:
            raise MyTurboSelfApiError("TurboSelf is unreachable") from err

        balance, meals_left, meal_price = self._parse_credits(credits_page)
        user_data = self._parse_user_data(home_page)
        latest_event = self._parse_latest_event(home_page)

        return AccountSnapshot(
            source="turboself_direct",
            balance=balance,
            meal_price=meal_price,
            remote_meals_left=meals_left,
            user_data=user_data,
            latest_event=latest_event,
        )

    async def _login(self, session: aiohttp.ClientSession) -> None:
        """Log in to TurboSelf."""

        homepage = await self._request(session, "GET", "Connexion.aspx")

        payload = {name: value for name, value in HOME_DATA_RE(homepage)}
        payload[LOGIN_USERNAME_FIELD] = self._username
        payload[LOGIN_PASSWORD_FIELD] = self._password

        response = await self._request(
            session,
            "POST",
            "Connexion.aspx",
            data=payload,
        )

        if self._looks_like_login_page(response):
            raise MyTurboSelfAuthError("TurboSelf rejected the credentials")

    async def _get_page(self, session: aiohttp.ClientSession, page_name: str) -> str:
        """Fetch an authenticated TurboSelf page."""

        return await self._request(
            session,
            "GET",
            page_name + ".aspx",
        )

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
    ) -> str:
        """Run an HTTP request and return the HTML body."""

        async with session.request(
            method,
            self._base_url + path,
            data=data,
        ) as response:
            response.raise_for_status()
            return await response.text()

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        """Return whether the response still looks like the login page."""

        return LOGIN_USERNAME_FIELD in html

    @staticmethod
    def _parse_credits(html: str) -> tuple[float, int | None, float | None]:
        """Parse balance, meals left and meal price."""

        extracted = ["".join(match) for match in CREDITS_RE(html)]
        values: list[float | int] = []

        for item in extracted:
            if not item:
                continue
            if "," in item:
                values.append(float(item.replace(",", ".")))
            else:
                values.append(int(item))

        if len(values) < 2:
            raise MyTurboSelfApiError("Could not parse the account balance")

        balance = float(values[0])
        meals_left = int(values[1]) if len(values) >= 2 else None
        meal_price = float(values[2]) if len(values) >= 3 else None
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

        match = HISTORY_ROW_RE.search(page_html)
        if match is None:
            return None

        columns = TD_RE.findall(match.group(1))
        if len(columns) < 2:
            return None

        value_match = re.search(r"<span[^>]*>(.*?)</span>", columns[1], re.DOTALL)
        if value_match is None:
            return None

        raw_value = _strip_tags(value_match.group(1))
        raw_name = _strip_tags(re.sub(r"<span[^>]*>.*?</span>", "", columns[1], flags=re.DOTALL))
        raw_date = _strip_tags(columns[0])

        try:
            event_date = datetime.strptime(raw_date, "%d/%m/%Y - %H:%M")
            numeric_value = float(raw_value.replace(",", "."))
        except ValueError:
            return None

        return AccountEvent(
            name=raw_name,
            date=event_date,
            value=numeric_value,
        )


def _strip_tags(value: str) -> str:
    """Remove HTML tags and normalize whitespace."""

    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return " ".join(text.split())
