"""`MediaStore` over Azure Blob Storage (ADR-114 decision 8: Small on Azure, where there is no S3).

References are the object-store adapter's own (`media/<sha256>.<ext>`, `reference_for` and
`checked` reused unchanged), so a file moved between the two stores keeps its name and a name
neither makes is refused before anything is read. Each reference is a block blob in the
deployment's media container.

No SDK: Blob's REST interface over `httpx`, signed with the account's Shared Key (Azure's
"Authorize with Shared Key"), the key held in the deployment's secrets store as every other
credential is. The signature is the one Azure checks; Azurite checks it the same way, which is
what the conformance run is against.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from email.utils import formatdate
from urllib.parse import urlsplit

import httpx

from adapters.media_objectstore import checked, reference_for
from ports.media import MediaNotFoundError

#: The REST version every request names (`x-ms-version`); Azurite 3.35 accepts it.
API_VERSION = "2025-01-05"


class BlobStoreError(RuntimeError):
    """Blob Storage refused a request; its status and message, unchanged."""


@dataclass(frozen=True)
class BlobStoreConfig:
    account: str
    key: str
    container: str = "ospreyflow-media"
    #: `https://<account>.blob.core.windows.net` on Azure; an emulator's address otherwise
    #: (Azurite's is path-style: `http://127.0.0.1:10000/<account>`).
    endpoint: str = ""

    @property
    def base(self) -> str:
        return (self.endpoint or f"https://{self.account}.blob.core.windows.net").rstrip("/")

    @classmethod
    def from_env(cls) -> BlobStoreConfig:
        return cls(
            account=os.environ["AZURE_STORAGE_ACCOUNT"],
            key=os.environ["AZURE_STORAGE_KEY"],
            container=os.environ.get("AZURE_MEDIA_CONTAINER", "ospreyflow-media"),
            endpoint=os.environ.get("AZURE_BLOB_ENDPOINT", ""),
        )


def string_to_sign(
    method: str, url: str, headers: dict[str, str], account: str, content_length: int
) -> str:
    """Azure's Shared Key string for the Blob service (version 2009-09-19 and later)."""
    parts = urlsplit(url)
    canonical_headers = "".join(
        f"{name}:{headers[name].strip()}\n"
        for name in sorted(h for h in headers if h.startswith("x-ms-"))
    )
    resource = f"/{account}{parts.path}"
    query = sorted(
        (name.lower(), value)
        for name, _, value in (pair.partition("=") for pair in parts.query.split("&") if pair)
    )
    resource += "".join(f"\n{name}:{value}" for name, value in query)
    return "\n".join(
        [
            method,
            "",  # Content-Encoding
            "",  # Content-Language
            str(content_length) if content_length else "",
            "",  # Content-MD5
            headers.get("content-type", ""),
            "",  # Date (x-ms-date is sent instead)
            "",  # If-Modified-Since
            "",  # If-Match
            "",  # If-None-Match
            "",  # If-Unmodified-Since
            "",  # Range
            canonical_headers + resource,
        ]
    )


def signed_headers(
    config: BlobStoreConfig, method: str, url: str, headers: dict[str, str], content_length: int
) -> dict[str, str]:
    full = {
        **{k.lower(): v for k, v in headers.items()},
        "x-ms-date": formatdate(usegmt=True),
        "x-ms-version": API_VERSION,
    }
    text = string_to_sign(method, url, full, config.account, content_length)
    digest = hmac.new(base64.b64decode(config.key), text.encode("utf-8"), hashlib.sha256).digest()
    full["authorization"] = f"SharedKey {config.account}:{base64.b64encode(digest).decode()}"
    return full


class BlobMediaStore:
    def __init__(self, config: BlobStoreConfig, http: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._http = http or httpx.AsyncClient(timeout=60.0)
        self._container_ready = False

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _send(
        self, method: str, url: str, *, content: bytes = b"", headers: dict[str, str] | None = None
    ) -> httpx.Response:
        signed = signed_headers(self._config, method, url, headers or {}, len(content))
        return await self._http.request(method, url, content=content, headers=signed)

    async def _ensure_container(self) -> None:
        # Made on first use, as the object-store adapter makes its bucket: a fresh deployment needs
        # no separate provisioning step. 409 is "already there".
        if self._container_ready:
            return
        response = await self._send(
            "PUT", f"{self._config.base}/{self._config.container}?restype=container"
        )
        if response.status_code not in (201, 409):
            raise BlobStoreError(f"{response.status_code}: {response.text}")
        self._container_ready = True

    def _url(self, ref: str) -> str:
        return f"{self._config.base}/{self._config.container}/{ref}"

    async def put(self, data: bytes, content_type: str) -> str:
        ref = reference_for(data, content_type)
        await self._ensure_container()
        response = await self._send(
            "PUT",
            self._url(ref),
            content=data,
            headers={"x-ms-blob-type": "BlockBlob", "content-type": content_type},
        )
        if response.status_code != 201:
            raise BlobStoreError(f"{response.status_code}: {response.text}")
        return ref

    async def get(self, ref: str) -> bytes:
        response = await self._send("GET", self._url(checked(ref)))
        if response.status_code == 404:
            raise MediaNotFoundError(ref)
        if response.status_code != 200:
            raise BlobStoreError(f"{response.status_code}: {response.text}")
        return response.content
