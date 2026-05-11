"""API wrapper used by the Home Assistant MyTurboSelf integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from bs4 import BeautifulSoup
import requests

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

HOME_DATA_RE = re.compile(r'name=\"(.*?)\".*value=\"(.*?)\"').findall
CREDITS_RE = re.compile(r"[>\n ]*?(\d+,\d+)|>Soit : (\d*) repas").findall
USER_KEY_RE = re.compile(r"ctl00_cntForm_UC_HeaderTop_lbl(.*)_Smartphone").findall


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
        self._session = requests.Session()

    def fetch_snapshot(self) -> AccountSnapshot:
        """Fetch the current TurboSelf account state."""

        if not self._username or not self._password:
            raise MyTurboSelfAuthError("TurboSelf credentials are not configured")

        try:
            self._login()
            credits_page = self._get_page("CrediterCompte")
            home_page = self._get_page("Accueil")
        except requests.RequestException as err:
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

    def _login(self) -> None:
        """Log in to TurboSelf."""

        homepage = self._session.get(
            self._base_url + "Connexion.aspx",
            timeout=TIMEOUT,
        )
        homepage.raise_for_status()

        payload = {name: value for name, value in HOME_DATA_RE(homepage.text)}
        payload[LOGIN_USERNAME_FIELD] = self._username
        payload[LOGIN_PASSWORD_FIELD] = self._password

        response = self._session.post(
            self._base_url + "Connexion.aspx",
            data=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        if self._looks_like_login_page(response.text):
            raise MyTurboSelfAuthError("TurboSelf rejected the credentials")

    def _get_page(self, page_name: str) -> str:
        """Fetch an authenticated TurboSelf page."""

        response = self._session.get(
            self._base_url + page_name + ".aspx",
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.text

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        """Return whether the response still looks like the login page."""

        soup = BeautifulSoup(html, "html.parser")
        return soup.find("input", {"name": LOGIN_USERNAME_FIELD}) is not None

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
    def _parse_user_data(html: str) -> dict[str, str]:
        """Parse user metadata from the account page."""

        soup = BeautifulSoup(html, "html.parser")
        modal_body = soup.find("div", {"class": "modal-body"})
        if modal_body is None:
            return {}

        data: dict[str, str] = {}
        for span in modal_body.find_all("span"):
            data_id = span.get("id")
            if not data_id:
                continue
            keys = USER_KEY_RE(data_id)
            if not keys:
                continue
            data[keys[0]] = span.text.strip()

        return data

    @staticmethod
    def _parse_latest_event(html: str) -> AccountEvent | None:
        """Parse the latest account event."""

        soup = BeautifulSoup(html, "html.parser")
        line = soup.find("tr", {"class": "rowHistoStyle"})
        if line is None:
            return None

        columns = line.find_all("td")
        if len(columns) < 2:
            return None

        value_span = columns[1].find("span")
        if value_span is None:
            return None

        raw_value = value_span.text.strip()
        raw_name = columns[1].text.replace(raw_value, "").strip()
        raw_date = columns[0].text.strip()

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
