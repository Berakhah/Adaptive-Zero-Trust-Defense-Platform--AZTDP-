import os

DB_URL = os.getenv("AZTDP_DB_URL", "postgresql://aztdp:aztdp@postgres:5432/aztdp")
POOL_MIN = int(os.getenv("AZTDP_DB_POOL_MIN", "2"))
POOL_MAX = int(os.getenv("AZTDP_DB_POOL_MAX", "10"))
