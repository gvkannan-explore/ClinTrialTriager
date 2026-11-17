import logging

import requests
from mcp.server.mcpserver import MCPServer
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(name="mcp-server-tools")

CLINICAL_TRIALS_URL = "https://clinicaltrials.gov/api/v2/studies"
EXPECTED_STATE = "Illinois"
EXPECTED_COUNTRY = "United States"
EXPECTED_STATUS = "RECRUITING"
MAX_PAGE_SIZE = 10
SEARCH_RADIUS = "50mi"
MAX_CRITERIA_CHARS = 6000

mcp = MCPServer("med-scout-mcp")


def flatten_study(
    study: dict,
    locations_limit: int = 3,
    state_loc: str = EXPECTED_STATE,
    country_loc: str = EXPECTED_COUNTRY,
) -> dict:
    """
    Helper function to retain necessary information from the study queried
    Args:
        study: One study from the ClinicalTrials.gov `studies` response.
        locations_limit: Maximum number of matching sites to keep.
        state_loc: Keep only sites in this state.
        country_loc: Keep only sites in this country.
    Returns:
        dict: The trial's nct_id, title, status and nearest_locations (empty list if no site matches).
    """
    study = {
        key: value
        for key, value in study["protocolSection"].items()
        if key in ["identificationModule", "statusModule", "contactsLocationsModule"]
    }

    contact_loc_info = []
    if "locations" not in study.get("contactsLocationsModule", {}):
        return {
            "nct_id": study["identificationModule"]["nctId"],
            "title": study["identificationModule"]["briefTitle"],
            "status": study["statusModule"]["overallStatus"],
            "nearest_locations": [],
        }

    for loc in study["contactsLocationsModule"]["locations"]:
        if (
            loc.get("country", "Missing") == country_loc
            and loc.get("state", "MISSING") == state_loc
        ):
            contact_loc_info.append(
                {
                    key: val
                    for key, val in loc.items()
                    if key in ["facility", "city", "state", "contacts"]
                }
            )
    study["contactsLocationsModule"]["locations"] = contact_loc_info[:locations_limit]
    return {
        "nct_id": study["identificationModule"]["nctId"],
        "title": study["identificationModule"]["briefTitle"],
        "status": study["statusModule"]["overallStatus"],
        "nearest_locations": study["contactsLocationsModule"]["locations"],
    }


@mcp.tool()
def search_trials(
    condition: str,
    terms: list[str],
    latitude: float,
    longitude: float,
    radius: str = SEARCH_RADIUS,
    status: str = EXPECTED_STATUS,
    state: str = EXPECTED_STATE,
    country: str = EXPECTED_COUNTRY,
    page_size: int = MAX_PAGE_SIZE,
) -> list[dict]:
    """
    Search ClinicalTrials.gov for trials with at least one site near the patient.
    Args:
        condition: The disease name only, e.g. "breast cancer".
        terms: 1-3 keywords, e.g. ["ESR1"]. Every term must match, so each extra term removes trials.
        latitude: Patient latitude, e.g. 41.88.
        longitude: Patient longitude, e.g. -87.62.
        radius: Search radius, e.g. "50mi".
        status: Trial status, e.g. "RECRUITING".
        state: Keep only sites in this state.
        country: Keep only sites in this country.
        page_size: Number of trials to fetch, at most 10.
    Returns:
        list[dict]: A list of dictionaries containing the flattened study information for each trial found.
    """
    query_params = {
        "query.cond": condition,
        "query.term": " ".join(terms),
        "filter.overallStatus": status,
        "pageSize": min(page_size, MAX_PAGE_SIZE),
        "filter.geo": f"distance({latitude},{longitude},{radius})",
    }
    if status == "NOT_YET_RECRUITING":
        logger.warning(
            "The pipeline might break as some of the entries with status `NOT_YET_RECRUITING` don't have locations."
        )
    try:
        query_response = requests.get(
            CLINICAL_TRIALS_URL, params=query_params, stream=True
        )
        query_response.raise_for_status()  # Raise an exception for HTTP errors
    except (RequestException, HTTPError) as e:
        raise RuntimeError(f"Error occurred while making the API request: {e}")

    studies = query_response.json().get("studies", [])
    flattened = (
        flatten_study(study, state_loc=state, country_loc=country) for study in studies
    )
    return [s for s in flattened if s["nearest_locations"]]


@mcp.tool()
def get_trial_details(nct_id: str) -> str:
    """
    Get the eligibility criteria text for one clinical trial.
    Args:
        nct_id: The trial's NCT ID, e.g. "NCT03723928".
    Returns:
        str: The inclusion and exclusion criteria, cut to 6000 characters and ending in "[truncated]" if longer.
    """
    try:
        query_response = requests.get(
            f"{CLINICAL_TRIALS_URL}/{nct_id}", stream=True, timeout=30
        )
        query_response.raise_for_status()  # Raise an exception for HTTP errors

    except (RequestException, HTTPError) as e:
        raise RuntimeError(f"Error occurred while making the API request: {e}")

    criteria = query_response.json()["protocolSection"]["eligibilityModule"][
        "eligibilityCriteria"
    ]
    if len(criteria) > MAX_CRITERIA_CHARS:
        logger.warning("Truncating eligibility criteria for %s", nct_id)
        return criteria[:MAX_CRITERIA_CHARS] + "[truncated]"
    return criteria


if __name__ == "__main__":
    logger.info("Running MCP server")
    mcp.run()
