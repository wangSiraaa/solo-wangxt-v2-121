import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://distill:distill@localhost:5432/distillation",
)
