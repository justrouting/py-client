"""The Geocode service: addresses into coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .error import InvalidRequestError
from .geo import Point

__all__ = [
    "GeocodeService",
    "GeocodeRequest",
    "StructuredQuery",
    "GeocodeResponse",
    "GeocodeQuery",
    "GeocodeResult",
    "Datasource",
    "Rank",
    "Timezone",
    "BBox",
]


@dataclass
class GeocodeRequest:
    """A forward-geocoding search. Exactly one of ``text`` and ``structured``
    must be set.

    Attributes:
        text: The free-form address to search for, such as "Marina Bay
            Sands, Singapore". Mutually exclusive with ``structured``.
        structured: An address given as typed components. Mutually
            exclusive with ``text``.
        limit: Cap the number of results. The API defaults to 5.
        offset: Skip the first ``offset`` results before applying
            ``limit``.
        filters: Restrict results, for example ``["countrycode:sg"]``.
            Each entry is sent as its own filter parameter; the API applies
            all of them.
        bias: Steer results toward a location, for example
            ``"proximity:103.8,1.3"``. It is forwarded verbatim.
        type: Restrict results to a feature type such as "street" or
            "city".
        lang: Request results in a language, such as "en".
    """

    text: str = ""
    structured: Optional["StructuredQuery"] = None
    limit: int = 0
    offset: int = 0
    filters: List[str] = field(default_factory=list)
    bias: str = ""
    type: str = ""
    lang: str = ""

    def query(self) -> dict:
        q: dict = {"format": "json"}
        if self.text:
            q["text"] = self.text
        if self.structured is not None:
            for key in [
                "name",
                "housenumber",
                "street",
                "postcode",
                "city",
                "state",
                "country",
            ]:
                value = getattr(self.structured, key)
                if value:
                    q[key] = value
        if self.limit > 0:
            q["limit"] = str(self.limit)
        if self.offset > 0:
            q["offset"] = str(self.offset)
        if self.filters:
            # Filter is repeatable; the list value is expanded into one
            # parameter per entry by the transport.
            q["filter"] = [f for f in self.filters if f]
            if not q["filter"]:
                del q["filter"]
        if self.bias:
            q["bias"] = self.bias
        if self.type:
            q["type"] = self.type
        if self.lang:
            q["lang"] = self.lang
        return q


@dataclass
class StructuredQuery:
    """An address expressed as typed fields. Only the fields that are set
    are sent."""

    name: str = ""
    housenumber: str = ""
    street: str = ""
    postcode: str = ""
    city: str = ""
    state: str = ""
    country: str = ""

    def any(self) -> bool:
        """Whether at least one structured field is set."""
        return any(
            [
                self.name,
                self.housenumber,
                self.street,
                self.postcode,
                self.city,
                self.state,
                self.country,
            ]
        )


@dataclass
class GeocodeResponse:
    """The result of a forward-geocoding search.

    Attributes:
        results: Ordered best first. Empty when nothing matches — an empty
            list is a valid answer, not an error.
        query: Echoes how the API interpreted the request, when returned.
    """

    results: List["GeocodeResult"] = field(default_factory=list)
    query: Optional["GeocodeQuery"] = None

    @classmethod
    def from_dict(cls, d: dict) -> "GeocodeResponse":
        query = d.get("query")
        return cls(
            results=[GeocodeResult.from_dict(r) for r in d.get("results") or []],
            query=GeocodeQuery.from_dict(query) if query else None,
        )


@dataclass
class GeocodeQuery:
    """How the API interpreted the request.

    Attributes:
        text: The free-text query as received by the API.
        parsed: The API's structured interpretation of ``text``. Its shape
            is not guaranteed, so it is preserved as the decoded JSON value.
    """

    text: str = ""
    parsed: Optional[Any] = None

    @classmethod
    def from_dict(cls, d: dict) -> "GeocodeQuery":
        return cls(
            text=d.get("text", ""),
            parsed=d.get("parsed"),
        )


@dataclass
class GeocodeResult:
    """One matching place.

    Attributes:
        lon, lat: The result's position as plain numbers, in the package's
            usual [longitude, latitude] order. Use [GeocodeResult.location]
            for a [Point].
        formatted: The full, human-readable address.
        distance: The metres from the bias location, present only when
            [GeocodeRequest.bias] is set.
    """

    datasource: Optional["Datasource"] = None
    housenumber: str = ""
    street: str = ""
    suburb: str = ""
    city: str = ""
    county: str = ""
    state: str = ""
    state_code: str = ""
    postcode: str = ""
    country: str = ""
    country_code: str = ""
    lon: float = 0.0
    lat: float = 0.0
    formatted: str = ""
    address_line1: str = ""
    address_line2: str = ""
    result_type: str = ""
    rank: Optional["Rank"] = None
    timezone: Optional["Timezone"] = None
    place_id: str = ""
    category: str = ""
    plus_code: str = ""
    name: str = ""
    bbox: Optional["BBox"] = None
    distance: float = 0.0

    def location(self) -> Point:
        """The result's position as a [Point], in [longitude, latitude]
        order."""
        return Point([self.lon, self.lat])

    @classmethod
    def from_dict(cls, d: dict) -> "GeocodeResult":
        datasource = d.get("datasource")
        rank = d.get("rank")
        timezone = d.get("timezone")
        bbox = d.get("bbox")
        return cls(
            datasource=Datasource.from_dict(datasource) if datasource else None,
            housenumber=d.get("housenumber", ""),
            street=d.get("street", ""),
            suburb=d.get("suburb", ""),
            city=d.get("city", ""),
            county=d.get("county", ""),
            state=d.get("state", ""),
            state_code=d.get("state_code", ""),
            postcode=d.get("postcode", ""),
            country=d.get("country", ""),
            country_code=d.get("country_code", ""),
            lon=d.get("lon", 0.0),
            lat=d.get("lat", 0.0),
            formatted=d.get("formatted", ""),
            address_line1=d.get("address_line1", ""),
            address_line2=d.get("address_line2", ""),
            result_type=d.get("result_type", ""),
            rank=Rank.from_dict(rank) if rank else None,
            timezone=Timezone.from_dict(timezone) if timezone else None,
            place_id=d.get("place_id", ""),
            category=d.get("category", ""),
            plus_code=d.get("plus_code", ""),
            name=d.get("name", ""),
            bbox=BBox.from_dict(bbox) if bbox else None,
            distance=d.get("distance", 0.0),
        )


@dataclass
class Datasource:
    """Credits the data provider of a [GeocodeResult]."""

    sourcename: str = ""
    attribution: str = ""
    license: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Datasource":
        return cls(
            sourcename=d.get("sourcename", ""),
            attribution=d.get("attribution", ""),
            license=d.get("license", ""),
            url=d.get("url", ""),
        )


@dataclass
class Rank:
    """Scores a [GeocodeResult]'s relevance and match confidence."""

    importance: float = 0.0
    popularity: float = 0.0
    confidence: float = 0.0
    confidence_city_level: float = 0.0
    confidence_street_level: float = 0.0
    match_type: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Rank":
        return cls(
            importance=d.get("importance", 0.0),
            popularity=d.get("popularity", 0.0),
            confidence=d.get("confidence", 0.0),
            confidence_city_level=d.get("confidence_city_level", 0.0),
            confidence_street_level=d.get("confidence_street_level", 0.0),
            match_type=d.get("match_type", ""),
        )


@dataclass
class Timezone:
    """A [GeocodeResult]'s time zone with standard- and daylight-time
    offsets."""

    name: str = ""
    offset_std: str = ""
    offset_std_seconds: int = 0
    offset_dst: str = ""
    offset_dst_seconds: int = 0
    abbreviation_std: str = ""
    abbreviation_dst: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Timezone":
        return cls(
            name=d.get("name", ""),
            offset_std=d.get("offset_STD", ""),
            offset_std_seconds=d.get("offset_STD_seconds", 0),
            offset_dst=d.get("offset_DST", ""),
            offset_dst_seconds=d.get("offset_DST_seconds", 0),
            abbreviation_std=d.get("abbreviation_STD", ""),
            abbreviation_dst=d.get("abbreviation_DST", ""),
        )


@dataclass
class BBox:
    """A bounding box as ``[lon1, lat1, lon2, lat2]``."""

    lon1: float = 0.0
    lat1: float = 0.0
    lon2: float = 0.0
    lat2: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "BBox":
        return cls(
            lon1=d.get("lon1", 0.0),
            lat1=d.get("lat1", 0.0),
            lon2=d.get("lon2", 0.0),
            lat2=d.get("lat2", 0.0),
        )


class GeocodeService:
    """Converts addresses into coordinates."""

    def __init__(self, transport) -> None:
        self._client = transport

    def search(
        self, req: GeocodeRequest, *, timeout: Optional[float] = None
    ) -> GeocodeResponse:
        """Matching places for ``req``, ordered best first.

            results = client.geocode.search(justrouting.GeocodeRequest(
                text="Marina Bay Sands, Singapore",
            ))
            print(results.results[0].formatted)

        An empty [GeocodeResponse.results] list means nothing matched; it
        is not an error.
        """
        if req is None:
            raise InvalidRequestError("justrouting: request must not be None")
        has_text = req.text != ""
        has_structured = req.structured is not None and req.structured.any()
        if has_text and has_structured:
            raise InvalidRequestError(
                "justrouting: Text and Structured are mutually exclusive"
            )
        if not has_text and not has_structured:
            raise InvalidRequestError(
                "justrouting: exactly one of Text or Structured is required"
            )
        if req.limit < 0:
            raise InvalidRequestError(
                f"justrouting: Limit must not be negative, got {req.limit}"
            )
        if req.offset < 0:
            raise InvalidRequestError(
                f"justrouting: Offset must not be negative, got {req.offset}"
            )
        return self._client.do(
            "GET",
            "/geocode/v1/search",
            query=req.query(),
            needs_auth=True,
            model=GeocodeResponse,
            timeout=timeout,
        )
