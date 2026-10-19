"""Bounded, credential-free HTTPS reachability check for the fixed SMASH server."""
from http.client import HTTPException
import ssl
from threading import Event, Thread
from urllib import error, request

from .nextcloud import NextcloudError, NoRedirect
from .settings import SMASH_URL


def probe_server(timeout=3.0, opener=None):
    """Do not read credentials, follow redirects or fetch clinical data.

    The daemon worker bounds the caller's wait even if system DNS resolution
    ignores the socket timeout. Late results never update the menu's state.
    """
    completed = Event()
    result = {"available": False, "detail": "HTTPS check timed out"}

    def check():
        try:
            client = opener or request.build_opener(NoRedirect(), request.HTTPSHandler(context=ssl.create_default_context()))
            ping = request.Request(SMASH_URL + "/status.php", method="HEAD")
            with client.open(ping, timeout=timeout) as response:
                code = response.status
            result.update(available=200 <= code < 300, detail="HTTPS reachable; login not checked" if 200 <= code < 300 else "HTTPS check failed (HTTP " + str(code) + ")")
        except error.HTTPError as exc:
            result.update(available=False, detail="HTTPS check failed (HTTP " + str(exc.code) + ")")
        except (OSError, ValueError, HTTPException, NextcloudError):
            # Never include server bodies, proxy details or exception text.
            result.update(available=False, detail="HTTPS connection unavailable")
        finally:
            completed.set()

    Thread(target=check, name="smash-https-check", daemon=True).start()
    if not completed.wait(timeout):
        return {"available": False, "detail": "HTTPS check timed out"}
    return dict(result)
