import os

DB_URL = os.getenv("AZTDP_DB_URL", "postgresql://aztdp:aztdp@postgres:5432/aztdp")
POOL_MIN = int(os.getenv("AZTDP_DB_POOL_MIN", "2"))
POOL_MAX = int(os.getenv("AZTDP_DB_POOL_MAX", "10"))
DEFAULT_PAGE_SIZE = int(os.getenv("AZTDP_FORENSICS_PAGE_SIZE", "100"))
MAX_PAGE_SIZE = int(os.getenv("AZTDP_FORENSICS_MAX_PAGE_SIZE", "500"))
INCIDENT_WINDOW_SECONDS = int(os.getenv("AZTDP_FORENSICS_INCIDENT_WINDOW", "5"))
