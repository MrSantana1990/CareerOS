"""Public, read-only ATS adapters used by the discovery worker."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
import urllib.parse
import urllib.request


ACCOUNT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,100}$")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def plain_text(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(value or ""))
    return " ".join(parser.parts)


@dataclass(frozen=True)
class NormalizedJob:
    source: str
    external_id: str
    source_url: str
    canonical_url: str
    company: str
    title: str
    description: str
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    work_model: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    application_channel: str = "ATS_API"

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


class JobSourceAdapter(ABC):
    source: str

    def __init__(self, account: str, company: str, timeout: int = 20) -> None:
        if not ACCOUNT_PATTERN.fullmatch(account):
            raise ValueError("Identificador de fonte inválido.")
        self.account = account
        self.company = company.strip()
        self.timeout = timeout
        if len(self.company) < 2:
            raise ValueError("Empresa inválida.")

    def fetch_json(self, url: str) -> dict | list:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "HelpSystemCareer/1.0"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Fonte respondeu HTTP {response.status}.")
            return json.loads(response.read().decode("utf-8"))

    @abstractmethod
    def discover(self) -> list[NormalizedJob]:
        raise NotImplementedError


class GreenhouseAdapter(JobSourceAdapter):
    source = "GREENHOUSE"

    def discover(self) -> list[NormalizedJob]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.account}/jobs?content=true"
        payload = self.fetch_json(url)
        return [self.normalize(item) for item in payload.get("jobs", []) if item.get("id")]

    def normalize(self, item: dict) -> NormalizedJob:
        canonical = item.get("absolute_url") or ""
        return NormalizedJob(
            source=self.source,
            external_id=str(item["id"]),
            source_url=canonical,
            canonical_url=canonical,
            company=self.company,
            title=item.get("title") or "Cargo não informado",
            description=plain_text(item.get("content")),
            location=(item.get("location") or {}).get("name"),
            application_channel="GREENHOUSE",
        )


class LeverAdapter(JobSourceAdapter):
    source = "LEVER"

    def discover(self) -> list[NormalizedJob]:
        account = urllib.parse.quote(self.account)
        payload = self.fetch_json(f"https://api.lever.co/v0/postings/{account}?mode=json")
        return [self.normalize(item) for item in payload if item.get("id")]

    def normalize(self, item: dict) -> NormalizedJob:
        categories = item.get("categories") or {}
        salary = item.get("salaryRange") or {}
        return NormalizedJob(
            source=self.source,
            external_id=str(item["id"]),
            source_url=item.get("hostedUrl") or "",
            canonical_url=item.get("hostedUrl") or "",
            company=self.company,
            title=item.get("text") or "Cargo não informado",
            description=item.get("descriptionPlain") or plain_text(item.get("description")),
            location=categories.get("location"),
            country=item.get("country"),
            employment_type=categories.get("commitment"),
            work_model=item.get("workplaceType"),
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            salary_currency=salary.get("currency"),
            salary_period=salary.get("interval"),
            application_channel="LEVER",
        )


class AshbyAdapter(JobSourceAdapter):
    source = "ASHBY"

    def discover(self) -> list[NormalizedJob]:
        account = urllib.parse.quote(self.account)
        payload = self.fetch_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{account}?includeCompensation=true"
        )
        return [self.normalize(item) for item in payload.get("jobs", []) if item.get("jobUrl")]

    def normalize(self, item: dict) -> NormalizedJob:
        compensation = item.get("compensation") or {}
        return NormalizedJob(
            source=self.source,
            external_id=str(item.get("id") or item["jobUrl"]),
            source_url=item["jobUrl"],
            canonical_url=item["jobUrl"],
            company=self.company,
            title=item.get("title") or "Cargo não informado",
            description=plain_text(item.get("descriptionHtml") or item.get("description")),
            location=item.get("location"),
            employment_type=item.get("employmentType"),
            work_model="REMOTE" if item.get("isRemote") else None,
            salary_min=compensation.get("minValue"),
            salary_max=compensation.get("maxValue"),
            salary_currency=compensation.get("currencyCode"),
            salary_period=compensation.get("interval"),
            application_channel="ASHBY",
        )


ADAPTERS = {adapter.source: adapter for adapter in (GreenhouseAdapter, LeverAdapter, AshbyAdapter)}


def build_adapter(source: str, account: str, company: str) -> JobSourceAdapter:
    adapter = ADAPTERS.get(source.upper())
    if not adapter:
        raise ValueError("Fonte não suportada.")
    return adapter(account, company)
