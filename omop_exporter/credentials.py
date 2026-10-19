"""Credential storage chosen explicitly by the interactive setup wizard."""
import importlib
import os
from pathlib import Path

from .nextcloud import NextcloudError, read_dotenv
from .settings import SMASH_URL, VAULT_SERVICE


def native_vault():
    try:
        keyring = importlib.import_module("keyring")
        backend = keyring.get_keyring()
        # Do not silently use null, plaintext, third-party or chained backends.
        allowed = ("keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService", "keyring.backends.kwallet")
        if type(backend).__module__ not in allowed or backend.priority <= 0:
            raise ValueError("Unsupported credential backend")
        return backend
    except Exception:
        raise NextcloudError('No supported OS credential vault is available. Install ".[secure]", or select session-only/.env storage.') from None


def save_vault(username, password, backend=None):
    try:
        (backend or native_vault()).set_password(VAULT_SERVICE, username, password)
    except NextcloudError:
        raise
    except Exception:
        raise NextcloudError("The OS credential vault could not save the app password") from None


def load_vault(username, backend=None):
    try:
        value = (backend or native_vault()).get_password(VAULT_SERVICE, username)
    except NextcloudError:
        raise
    except Exception:
        raise NextcloudError("The OS credential vault could not read the app password") from None
    if not value:
        raise NextcloudError("No saved app password was found; run setup again")
    return value


def save_env(path, username, password):
    """Explicit plaintext opt-in. Retain unrelated settings, strip old credentials."""
    path = Path(path)
    if not (path.name == ".env" or path.name.startswith(".env.")) or path.name.endswith(".example"):
        raise NextcloudError("Plaintext credentials must use .env or .env.local, not a template or other project file")
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    remove = {"NEXTCLOUD_URL", "NEXTCLOUD_USERNAME", "NEXTCLOUD_PASSWORD"}
    retained = []
    for line in lines:
        assignment = line.strip()
        if assignment.startswith("export "):
            assignment = assignment[7:]
        if assignment.partition("=")[0].strip() not in remove:
            retained.append(line)
    for value in (username, password):
        if any(ord(c) < 32 for c in value):
            raise NextcloudError("Credentials cannot contain control characters")
    retained += ["NEXTCLOUD_URL=" + SMASH_URL, "NEXTCLOUD_USERNAME='" + username + "'", "NEXTCLOUD_PASSWORD='" + password + "'"]
    # rfind-based literal dotenv parsing also preserves embedded quote characters.
    content = "\n".join(retained) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".setup-part")
    if temporary.exists():
        raise NextcloudError("A previous .env setup staging file exists; inspect it before retrying")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def env_credentials(path):
    return read_dotenv(path) if Path(path).exists() else {}
