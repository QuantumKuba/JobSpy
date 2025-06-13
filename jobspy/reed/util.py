from __future__ import annotations

import re
from typing import Optional

from jobspy.model import JobType, Location, Country
from jobspy.reed.constant import REED_REMOTE_PATTERNS


def is_job_remote(location_name: str | None, description: str | None) -> bool:
    """
    Determine if a job is remote based on location and description
    """
    if not location_name and not description:
        return False

    text_to_check = []
    if location_name:
        text_to_check.append(location_name.lower())
    if description:
        text_to_check.append(description.lower())

    combined_text = " ".join(text_to_check)

    return any(pattern in combined_text for pattern in REED_REMOTE_PATTERNS)


def parse_location(location_name: str | None) -> Location | None:
    """
    Parse location string from Reed API into Location object
    """
    if not location_name:
        return None

    location_name = location_name.strip()

    # Reed typically provides location in format "City, County" or "City"
    # Since it's UK-focused, we default to UK country
    parts = location_name.split(",")
    city = parts[0].strip() if parts else location_name
    state = parts[1].strip() if len(parts) > 1 else None

    return Location(city=city, state=state, country=Country.UK)


def extract_job_id_from_url(job_url: str) -> str | None:
    """
    Extract job ID from Reed job URL
    """
    # Reed URLs are typically: https://www.reed.co.uk/jobs/123456789
    match = re.search(r"/jobs/(\d+)", job_url)
    return match.group(1) if match else None


def format_reed_search_params(
    keywords: str | None = None,
    location_name: str | None = None,
    distance: int = 10,
    is_remote: bool = False,
    job_type: JobType | None = None,
    hours_old: int | None = None,
    results_to_take: int = 100,
    results_to_skip: int = 0,
) -> dict[str, str | int]:
    """
    Format search parameters for Reed API
    """
    params: dict[str, str | int] = {
        "resultsToTake": min(results_to_take, 100),  # Reed API max
        "resultsToSkip": results_to_skip,
        "distanceFromLocation": min(distance, 100),  # Reed API max distance
    }

    if keywords:
        params["keywords"] = keywords

    # For remote jobs, don't specify location
    if location_name and not is_remote:
        params["locationName"] = location_name

    # Handle job type filtering
    if job_type:
        if job_type == JobType.FULL_TIME:
            params["fullTime"] = "true"
        elif job_type == JobType.PART_TIME:
            params["partTime"] = "true"
        elif job_type == JobType.CONTRACT:
            params["contract"] = "true"
        elif job_type == JobType.TEMPORARY:
            params["temp"] = "true"
        # Reed also supports permanent filter
        if job_type == JobType.FULL_TIME:
            params["permanent"] = "true"

    # Reed API doesn't directly support hours_old filter
    # This would typically be handled by filtering results after fetching

    return {k: v for k, v in params.items() if v is not None}


def validate_reed_api_key(api_key: str | None) -> bool:
    """
    Basic validation of Reed API key format
    Reed API keys are typically UUIDs
    """
    if not api_key:
        return False

    # Reed API keys are typically in UUID format
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    return bool(uuid_pattern.match(api_key))
