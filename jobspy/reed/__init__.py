from __future__ import annotations

import os
import base64
from datetime import datetime, date
from typing import Optional
import requests

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    Location,
    Country,
    Compensation,
    CompensationInterval,
    JobType,
)
from jobspy.util import create_logger, create_session
from jobspy.reed.util import (
    is_job_remote,
    parse_location,
    format_reed_search_params,
    validate_reed_api_key,
)
from jobspy.reed.constant import REED_BASE_URL

log = create_logger("Reed")


class ReedScraper(Scraper):
    base_url = REED_BASE_URL

    def __init__(
        self,
        proxies: list[str] | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
        api_key: str | None = None,
    ):
        super().__init__(
            Site.REED, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.api_key = api_key or os.getenv("REED_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Reed API key is required. Please set REED_API_KEY environment variable "
                "or pass api_key parameter. You can get your API key from https://www.reed.co.uk/developers"
            )

        if not validate_reed_api_key(self.api_key):
            log.warning("Reed API key format appears invalid. Expected UUID format.")

        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False, has_retry=True  # type: ignore
        )
        # Set up basic authentication with API key as username
        auth_string = f"{self.api_key}:"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        self.session.headers.update(
            {
                "Authorization": f"Basic {encoded_auth}",
                "User-Agent": self.user_agent or "JobSpy-Reed-Scraper/1.0",
            }
        )

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        job_list: list[JobPost] = []

        results_wanted = scraper_input.results_wanted or 15
        results_per_page = min(100, results_wanted)  # Reed API max is 100
        results_to_skip = scraper_input.offset or 0

        total_fetched = 0

        while total_fetched < results_wanted:
            remaining_results = results_wanted - total_fetched
            current_page_size = min(results_per_page, remaining_results)

            log.info(
                f"Fetching Reed jobs - skip: {results_to_skip}, take: {current_page_size}"
            )

            jobs_batch = self._fetch_jobs(
                keywords=scraper_input.search_term,
                location_name=scraper_input.location,
                distance=scraper_input.distance or 10,
                results_to_take=current_page_size,
                results_to_skip=results_to_skip,
                is_remote=scraper_input.is_remote,
                job_type=scraper_input.job_type,
                hours_old=scraper_input.hours_old,
            )

            if not jobs_batch:
                log.info("No more jobs found")
                break

            for job_data in jobs_batch:
                try:
                    job_post = self._parse_job(job_data)
                    if job_post:
                        job_list.append(job_post)
                        total_fetched += 1
                        if total_fetched >= results_wanted:
                            break
                except Exception as e:
                    log.error(f"Error parsing job: {e}")
                    continue

            if len(jobs_batch) < current_page_size:
                log.info("Reached end of available jobs")
                break

            results_to_skip += len(jobs_batch)

        return JobResponse(jobs=job_list)

    def _fetch_jobs(
        self,
        keywords: str | None = None,
        location_name: str | None = None,
        distance: int = 10,
        results_to_take: int = 100,
        results_to_skip: int = 0,
        is_remote: bool = False,
        job_type: JobType | None = None,
        hours_old: int | None = None,
    ) -> list[dict] | None:
        """
        Fetch jobs from Reed API
        """
        try:
            params = format_reed_search_params(
                keywords=keywords,
                location_name=location_name,
                distance=distance,
                is_remote=is_remote,
                job_type=job_type,
                hours_old=hours_old,
                results_to_take=results_to_take,
                results_to_skip=results_to_skip,
            )

            url = f"{self.base_url}/search"
            log.debug(f"Reed API request: {url} with params: {params}")

            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if isinstance(data, dict) and "results" in data:
                jobs = data["results"]
            elif isinstance(data, list):
                jobs = data
            else:
                log.warning(f"Unexpected response format: {type(data)}")
                return []

            log.info(f"Found {len(jobs)} jobs from Reed API")
            return jobs

        except requests.exceptions.RequestException as e:
            log.error(f"Reed API request failed: {e}")
            return None
        except Exception as e:
            log.error(f"Error fetching Reed jobs: {e}")
            return None

    def _parse_job(self, job_data: dict) -> JobPost | None:
        """
        Parse a job from Reed API response
        """
        try:
            # Extract basic job information
            job_id = str(job_data.get("jobId", ""))
            title = job_data.get("jobTitle", "").strip()
            company_name = job_data.get("employerName", "").strip()

            if not title:
                return None

            # Build job URLs
            job_url = (
                f"https://www.reed.co.uk/jobs/{job_id}"
                if job_id
                else f"https://www.reed.co.uk/jobs/unknown-{hash(title)}"
            )
            external_url = job_data.get("externalUrl")
            job_url_direct = external_url if external_url else job_url

            # Parse location
            location = parse_location(job_data.get("locationName"))

            # Parse compensation
            compensation = None
            min_salary = job_data.get("minimumSalary")
            max_salary = job_data.get("maximumSalary")

            if min_salary is not None or max_salary is not None:
                # Reed API returns annual salaries
                compensation = Compensation(
                    min_amount=float(min_salary) if min_salary else None,
                    max_amount=float(max_salary) if max_salary else None,
                    currency="GBP",
                    interval=CompensationInterval.YEARLY,
                )

            # Parse job type - Reed API doesn't provide detailed job type info in search results
            job_type_list = []

            # Get job description if available (usually only available via detailed job API)
            description = job_data.get("jobDescription", "").strip()

            # Reed API doesn't provide date posted in search results
            date_posted = None

            # Check if job is remote based on location or description
            remote_check = is_job_remote(
                location_name=job_data.get("locationName"), description=description
            )

            # Create job post
            job_post = JobPost(
                id=job_id,
                title=title,
                company_name=company_name,
                job_url=job_url,
                job_url_direct=job_url_direct,
                location=location,
                description=description if description else None,
                compensation=compensation,
                date_posted=date_posted,
                job_type=job_type_list if job_type_list else None,
                is_remote=remote_check,
            )

            return job_post

        except Exception as e:
            log.error(f"Error parsing Reed job: {e}")
            return None

    def get_job_details(self, job_id: str) -> dict | None:
        """
        Get detailed job information from Reed API
        This method can be used to fetch additional details for a specific job
        """
        try:
            url = f"{self.base_url}/jobs/{job_id}"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            log.error(f"Error fetching Reed job details for {job_id}: {e}")
            return None
