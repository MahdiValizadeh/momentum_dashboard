"""
config.py
Application configuration.
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "momentum.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Default skills seeded on first run
    DEFAULT_SKILLS = [
        {"name": "Python", "color": "#3776AB"},
        {"name": "Linux", "color": "#FCC624"},
        {"name": "English", "color": "#DC3545"},
        {"name": "Workout", "color": "#198754"},
    ]
