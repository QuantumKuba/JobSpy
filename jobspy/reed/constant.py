# Reed.co.uk API constants

# Reed API endpoints
REED_BASE_URL = "https://www.reed.co.uk/api/1.0"
REED_SEARCH_ENDPOINT = "/search"
REED_JOB_DETAILS_ENDPOINT = "/jobs"

# Reed API limits
REED_MAX_RESULTS_PER_PAGE = 100
REED_MAX_DISTANCE = 100  # miles

# Default headers for Reed API
REED_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Reed job types mapping to JobSpy JobType
REED_JOB_TYPE_MAPPING = {
    "permanent": "permanent",
    "contract": "contract",
    "temp": "temporary",
    "partTime": "part_time",
    "fullTime": "full_time",
}

# Common Reed location patterns for remote work detection
REED_REMOTE_PATTERNS = [
    "remote",
    "work from home",
    "wfh",
    "home based",
    "anywhere in uk",
    "location flexible",
]
