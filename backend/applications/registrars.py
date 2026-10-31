"""Bounded public registrar adapters. No challenge solving or financial writes.

Only documented fields are normalized; missing results are never zero allotment.
Public issue catalogues may be cached, but applicant responses must not be cached.
"""

import http.client
import json
import re
import ssl
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import certifi
from django.core.cache import cache

KFIN_SITE = "https://ipostatus.kfintech.com/"
# Same public asset request headers observed in the founder's browser. The
# site serves its HTML shell for the JS bundle to unrecognized user agents.
KFIN_ASSET_HEADERS = {
    "accept": "*/*",
    "referer": KFIN_SITE,
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
}
KFIN_API = "https://0uz601ms56.execute-api.ap-south-1.amazonaws.com/prod/api/query?type=pan"
MUFG_API = "https://in.mpms.mufg.com/Initial_Offer/IPO.aspx/"
BIGSHARE_SITE = "https://ipo.bigshareonline.com/"
MAX_BODY = 4 * 1024 * 1024
PROVIDERS = ("kfin", "mufg", "bigshare")


class RegistrarError(Exception):
    def __init__(self, state="UNAVAILABLE"):
        self.state = state
        super().__init__(state)


def request(url, *, body=None, headers=None):
    # Fixed destinations only. http.client preserves the lower-case registrar
    # header contract (urllib changes reqparam/client_id casing).
    target = urlsplit(url)
    connection = http.client.HTTPSConnection(
        target.hostname,
        timeout=6,
        context=ssl.create_default_context(cafile=certifi.where()),
    )
    try:
        connection.request(
            "POST" if body is not None else "GET",
            target.path + ("?" + target.query if target.query else ""),
            body=json.dumps(body).encode() if body is not None else None,
            headers={
                "accept": "application/json, text/plain, */*",
                **({"content-type": "application/json"} if body is not None else {}),
                **(headers or {}),
            },
        )
        response = connection.getresponse()
        if response.status == 429:
            raise RegistrarError("RATE_LIMITED")
        if response.status != 200:
            raise RegistrarError()
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise RegistrarError()
        return raw.decode("utf-8-sig")
    except (OSError, UnicodeError, ValueError, http.client.HTTPException):
        # Error text can echo private headers. Never propagate/log it.
        raise RegistrarError() from None
    finally:
        connection.close()


def get_json(url, **kwargs):
    try:
        return json.loads(request(url, **kwargs))
    except (ValueError, TypeError):
        raise RegistrarError() from None


def count(value):
    if isinstance(value, bool) or value is None:
        raise RegistrarError("REVIEW")
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"\d{1,9}", text):
        raise RegistrarError("REVIEW")
    return int(text)


def identifier(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def category(value):
    return {
        "RETAIL": "RETAIL",
        "RII": "RETAIL",
        "SHARE": "SHARE",
        "SHAREHOLDER": "SHARE",
        "SHAREHOLDERS": "SHARE",
        "SHNI": "SHNI",
        "SMALLNII": "SHNI",
        "BHNI": "BHNI",
        "BIGNII": "BHNI",
    }.get(identifier(value), "")


@dataclass(frozen=True)
class Bid:
    quantity: int
    applied: int | None = None
    reference: str = ""
    demat: str = ""
    category: str = ""

    def data(self):
        return asdict(self)


def _bid(row, *, quantity, applied, reference, demat, quota=""):
    return Bid(
        count(row.get(quantity)),
        count(row[applied]) if str(row.get(applied, "")).strip() else None,
        str(row.get(reference) or "")[:100],
        str(row.get(demat) or "")[:100],
        category(row.get(quota)),
    )


def xml_rows(value):
    if not isinstance(value, str) or "<!" in value.upper() or len(value) > MAX_BODY:
        raise RegistrarError()
    try:
        root = ElementTree.fromstring(value)
    except ElementTree.ParseError:
        raise RegistrarError() from None
    return [{child.tag: child.text or "" for child in node} for node in root if list(node)]


def parse_bids(provider, payload, pan):
    if provider == "kfin":
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) > 100:
            raise RegistrarError()
        bids = []
        for row in rows:
            if not isinstance(row, dict):
                raise RegistrarError()
            if re.search(r"no\s*record|not\s*found|not\s*applied", str(row.get("Name", "")), re.I):
                continue
            returned_pan = identifier(row.get("Pan_No"))
            # KFin masks the first six PAN characters in its response. Accept
            # only the exact full PAN or that known mask with the expected suffix.
            if returned_pan and returned_pan not in {pan, "XXXXXX" + pan[-4:]}:
                raise RegistrarError("REVIEW")
            bids.append(
                _bid(
                    row,
                    quantity="All_Shares",
                    applied="App_Shares",
                    reference="Appln_No",
                    demat="DP_CLID",
                    quota="Category",
                )
            )
        return bids
    if provider == "mufg":
        rows = xml_rows(payload.get("d") if isinstance(payload, dict) else None)
        bids = []
        for row in rows:
            # Table1 contains headings / notices on some issues, not another bid.
            if "ALLOT" not in row:
                if any(re.search(r"captcha|verify", str(v), re.I) for v in row.values()):
                    raise RegistrarError("CHALLENGE")
                if any(re.search(r"pending|not.*published", str(v), re.I) for v in row.values()):
                    raise RegistrarError("PENDING")
                continue
            bids.append(
                _bid(
                    row,
                    quantity="ALLOT",
                    applied="SHARES",
                    reference="PEMNDG",
                    demat="DPCLID",
                    quota="CATEGORY",
                )
            )
        return bids
    if provider == "bigshare":
        data = payload.get("d") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RegistrarError()
        state = str(data.get("Status", "")).upper()
        if state == "CAPTCHA":
            raise RegistrarError("CHALLENGE")
        if state in {"NOTFOUND", "NO_RECORD", "NO_DATA", "NODATA"}:
            return []
        if state and state != "OK":
            raise RegistrarError("REVIEW")
        rows = data.get("Records")
        if rows is None:
            if int(data.get("MatchCount") or 1) > 1:
                raise RegistrarError("REVIEW")
            rows = [data]
        if not isinstance(rows, list) or len(rows) > 100:
            raise RegistrarError()
        if data.get("MatchCount") is not None and count(data["MatchCount"]) != len(rows):
            raise RegistrarError("REVIEW")
        return [
            _bid(
                row,
                quantity="ALLOTED",
                applied="APPLIED",
                reference="APPLICATION_NO",
                demat="DPID",
                quota="CATEGORY",
            )
            for row in rows
        ]
    raise RegistrarError("UNSUPPORTED")


class IssueOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_select = False
        self.value = None
        self.name = ""
        self.options = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_select = attrs.get("id") == "ddlCompany"
        if self.in_select and tag == "option":
            self.value = attrs.get("value", "")
            self.name = ""

    def handle_data(self, data):
        if self.value is not None:
            self.name += data

    def handle_endtag(self, tag):
        if tag == "option" and self.value is not None:
            if self.value.isdigit() and int(self.value) > 0 and self.name.strip():
                self.options.append({"id": self.value, "name": self.name.strip()})
            self.value = None
        if tag == "select":
            self.in_select = False


def catalogue(provider):
    key = f"allotment:catalogue:v1:{provider}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        if provider == "kfin":
            html = request(KFIN_SITE, headers=KFIN_ASSET_HEADERS)
            match = re.search(r"(?:\./)?(static/js/main\.[a-zA-Z0-9]+\.js)", html)
            if not match:
                raise RegistrarError()
            bundle = request(urljoin(KFIN_SITE, match[1]), headers=KFIN_ASSET_HEADERS)
            # Extract only JSON. Never evaluate remote JavaScript.
            match = re.search(r'\[\s*\{\s*\\?"clientId\\?"[\s\S]{1,100000}?\}\s*\]', bundle)
            if not match:
                raise RegistrarError()
            raw = json.loads(match[0].replace('\\"', '"'))
            rows = [{"id": str(r["clientId"]), "name": str(r["name"])} for r in raw]
        elif provider == "mufg":
            payload = get_json(MUFG_API + "GetDetails", body={})
            rows = [
                {"id": r["company_id"], "name": r["companyname"]}
                for r in xml_rows(payload.get("d"))
                if "company_id" in r and "companyname" in r
            ]
        elif provider == "bigshare":
            parser = IssueOptions()
            parser.feed(request(BIGSHARE_SITE + "ipo_status.html"))
            rows = parser.options
        else:
            raise RegistrarError("UNSUPPORTED")
        if not rows or len(rows) > 1000:
            raise RegistrarError()
        rows = [r for r in rows if re.fullmatch(r"[A-Za-z0-9-]{1,50}", r["id"])]
        cache.set(key, rows, 3600)
        return rows
    except (RegistrarError, ValueError, KeyError, TypeError):
        # A short negative cache prevents an outage causing repeated catalogue requests.
        cache.set(key, [], 60)
        return []


def issue_name(value):
    words = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip().split()
    while words and words[-1] in {"IPO", "LIMITED", "LTD"}:
        words.pop()
    return " ".join(words)


def resolve_issue(ipo, catalogues):
    matches = [
        (p, r["id"])
        for p, rows in catalogues.items()
        for r in rows
        if issue_name(r["name"]) == issue_name(ipo.issuer_name)
    ]
    return matches[0] if len(matches) == 1 else None


def lookup(provider, issue_id, pan):
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        raise RegistrarError("REVIEW")
    if provider == "kfin":
        payload = get_json(
            KFIN_API,
            headers={
                "reqparam": pan,
                "client_id": issue_id,
                "Origin": KFIN_SITE.rstrip("/"),
                "Referer": KFIN_SITE,
            },
        )
    elif provider == "mufg":
        payload = get_json(
            MUFG_API + "SearchOnPan",
            body={
                "clientid": issue_id,
                "PAN": pan,
                "IFSC": "",
                "CHKVAL": "1",
                "token": "",
            },
        )
    elif provider == "bigshare":
        payload = get_json(
            BIGSHARE_SITE + "Data.aspx/FetchIpodetails",
            body={
                "Applicationno": "",
                "Company": issue_id,
                "SelectionType": "PN",
                "PanNo": pan,
                "txtcsdl": "",
                "txtDPID": "",
                "txtClId": "",
                "ddlType": "",
                "lang": "en",
            },
        )
    else:
        raise RegistrarError("UNSUPPORTED")
    try:
        return parse_bids(provider, payload, pan)
    except (TypeError, ValueError, KeyError, AttributeError):
        raise RegistrarError("REVIEW") from None
