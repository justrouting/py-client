"""Port of geocode_test.go."""

import pytest

import justrouting
from conftest import json_handler, new_test_client

# geocodeFixture mirrors a real geocoding response: one result with every
# optional field populated, and the query echoed back.
GEOCODE_FIXTURE = """{
  "results": [{
    "datasource": {
      "sourcename": "openstreetmap",
      "attribution": "© OpenStreetMap contributors",
      "license": "Open Database License",
      "url": "https://www.openstreetmap.org/copyright"
    },
    "name": "Marina Bay Sands",
    "housenumber": "10",
    "street": "Bayfront Avenue",
    "city": "Singapore",
    "county": "Singapore",
    "state": "Singapore",
    "postcode": "018956",
    "country": "Singapore",
    "country_code": "sg",
    "lon": 103.859,
    "lat": 1.2834,
    "formatted": "Marina Bay Sands, 10 Bayfront Avenue, 018956, Singapore",
    "address_line1": "Marina Bay Sands",
    "address_line2": "10 Bayfront Avenue, 018956, Singapore",
    "result_type": "building",
    "rank": {
      "importance": 0.4,
      "popularity": 4.0,
      "confidence": 1,
      "confidence_city_level": 1,
      "confidence_street_level": 1,
      "match_type": "full_match"
    },
    "timezone": {
      "name": "Asia/Singapore",
      "offset_STD": "+08:00",
      "offset_STD_seconds": 28800,
      "offset_DST": "+08:00",
      "offset_DST_seconds": 28800,
      "abbreviation_STD": "+08",
      "abbreviation_DST": "+08"
    },
    "place_id": "51667b3e1416f7594059aad55757058af43ff00103f9018322790001000000c0",
    "category": "tourism.hotel",
    "plus_code": "7VH8V75X+9X",
    "bbox": {"lon1": 103.8574, "lat1": 1.2822, "lon2": 103.8605, "lat2": 1.2846},
    "distance": 1234
  }],
  "query": {
    "text": "Marina Bay Sands, Singapore",
    "parsed": {"city": "singapore", "country": "singapore", "expected_type": "building"}
  }
}"""


def simple_geocode():
    return justrouting.GeocodeRequest(text="Marina Bay Sands")


def test_geocode_search_decodes_response():
    with new_test_client(json_handler(200, GEOCODE_FIXTURE)) as c:
        resp = c.geocode.search(simple_geocode())

    assert len(resp.results) == 1
    r = resp.results[0]

    assert r.formatted == "Marina Bay Sands, 10 Bayfront Avenue, 018956, Singapore"
    assert r.street == "Bayfront Avenue"
    assert r.country_code == "sg"
    assert (r.lon, r.lat) == (103.859, 1.2834)
    assert r.rank.confidence == 1
    assert r.timezone.name == "Asia/Singapore"
    assert r.place_id == "51667b3e1416f7594059aad55757058af43ff00103f9018322790001000000c0"
    assert r.plus_code == "7VH8V75X+9X"
    assert r.bbox.lon2 == 103.8605
    assert r.distance == 1234

    loc = r.location()
    assert loc.lon() == 103.859
    assert loc.lat() == 1.2834
    loc.validate()  # must be a well-formed [longitude, latitude] pair

    assert resp.query is not None
    assert resp.query.text == "Marina Bay Sands, Singapore"
    assert resp.query.parsed["city"] == "singapore"


# An empty result list is a valid answer, not an error.
def test_geocode_search_empty_results():
    with new_test_client(json_handler(200, '{"results":[]}')) as c:
        resp = c.geocode.search(justrouting.GeocodeRequest(text="nowhere"))

    assert len(resp.results) == 0
    assert resp.query is None


@pytest.mark.parametrize(
    "req,want,omitted",
    [
        (
            justrouting.GeocodeRequest(text="Orchard Road"),
            {"format": "json", "text": "Orchard Road"},
            [
                "name", "housenumber", "street", "postcode", "city", "state",
                "country", "limit", "offset", "filter", "bias", "type", "lang",
            ],
        ),
        (
            justrouting.GeocodeRequest(
                structured=justrouting.StructuredQuery(
                    name="Marina Bay Sands",
                    housenumber="10",
                    street="Bayfront Avenue",
                    postcode="018956",
                    city="Singapore",
                    state="Singapore",
                    country="Singapore",
                )
            ),
            {
                "format": "json",
                "name": "Marina Bay Sands",
                "housenumber": "10",
                "street": "Bayfront Avenue",
                "postcode": "018956",
                "city": "Singapore",
                "state": "Singapore",
                "country": "Singapore",
            },
            ["text"],
        ),
    ],
)
def test_geocode_request_encoding(req, want, omitted):
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, '{"results":[]}', {}

    with new_test_client(handler) as c:
        c.geocode.search(req)

    for key, value in want.items():
        assert seen["query"][key] == [value]
    for key in omitted:
        assert key not in seen["query"]


def test_geocode_request_encoding_all_options():
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, '{"results":[]}', {}

    with new_test_client(handler) as c:
        c.geocode.search(
            justrouting.GeocodeRequest(
                text="Orchard Road",
                limit=5,
                offset=10,
                filters=["countrycode:sg", "city:singapore"],
                bias="proximity:103.8,1.3",
                type="street",
                lang="en",
            )
        )

    for key, value in {
        "format": "json",
        "text": "Orchard Road",
        "limit": "5",
        "offset": "10",
        "bias": "proximity:103.8,1.3",
        "type": "street",
        "lang": "en",
    }.items():
        assert seen["query"][key] == [value]
    # Filter is repeatable; both values arrive in the order given.
    assert seen["query"]["filter"] == ["countrycode:sg", "city:singapore"]


def test_geocode_request_encoding_zero_values_omitted():
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, '{"results":[]}', {}

    with new_test_client(handler) as c:
        c.geocode.search(justrouting.GeocodeRequest(text="Orchard Road", filters=[""]))

    assert seen["query"] == {"format": ["json"], "text": ["Orchard Road"]}


@pytest.mark.parametrize(
    "req",
    [
        None,  # nil request
        justrouting.GeocodeRequest(  # text and structured together
            text="x", structured=justrouting.StructuredQuery(city="Singapore")
        ),
        justrouting.GeocodeRequest(),  # neither input
        justrouting.GeocodeRequest(  # empty structured
            structured=justrouting.StructuredQuery()
        ),
        justrouting.GeocodeRequest(text="x", limit=-1),  # negative limit
        justrouting.GeocodeRequest(text="x", offset=-1),  # negative offset
    ],
)
def test_geocode_validation(req):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(justrouting.InvalidRequestError):
            c.geocode.search(req)


# Upstream geocoding errors pass through the gateway with their own body
# shape; classification must still map them onto the usual exceptions.
def test_geocode_error_passthrough():
    with new_test_client(
        json_handler(
            401,
            '{"statusCode":401,"error":"Unauthorized","message":"Invalid apiKey"}',
        ),
        max_retries=0,
    ) as c:
        with pytest.raises(justrouting.UnauthorizedError) as e:
            c.geocode.search(justrouting.GeocodeRequest(text="Singapore"))
    assert e.value.status_code == 401
    # The Go client prefers the "message" field; the Python client prefers
    # "error" (see error.py), so the body decodes differently.
    assert e.value.message == "Unauthorized"

    with new_test_client(
        json_handler(502, '{"error":"upstream unavailable"}'), max_retries=0
    ) as c:
        with pytest.raises(justrouting.UpstreamUnavailableError):
            c.geocode.search(justrouting.GeocodeRequest(text="Singapore"))
