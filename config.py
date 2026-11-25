"""
config.py
Application configuration.
"""
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_or_create_secret_key():
    """Use SECRET_KEY from the environment, else persist a random one per install."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    instance_dir = os.path.join(BASE_DIR, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    key_path = os.path.join(instance_dir, "secret.key")
    if os.path.exists(key_path):
        with open(key_path, encoding="utf-8") as fh:
            stored = fh.read().strip()
        if stored:
            return stored
    generated = secrets.token_hex(32)
    with open(key_path, "w", encoding="utf-8") as fh:
        fh.write(generated)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return generated


class Config:
    SECRET_KEY = _load_or_create_secret_key()
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
