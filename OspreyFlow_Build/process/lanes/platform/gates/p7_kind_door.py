"""A pytest plugin for P7's acceptance run on the kind cluster (`p7_kind.sh accept`): the
deployment's own names (`*.p7.test`, synthetic) resolved to the kind node that holds the ingress
controller, and the stand-in CA that signed the Ingress's certificate trusted. Nothing else is
changed: every call still goes through the Ingress, by name, over TLS, as a browser's would.
"""

import os
import socket
import ssl

import httpx

_INGRESS = os.environ["P7_INGRESS_IP"]
_CONTEXT = ssl.create_default_context(cafile=os.environ["P7_CA_FILE"])
_getaddrinfo = socket.getaddrinfo


def _resolve(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    if isinstance(host, str) and host.endswith("p7.test"):
        host = _INGRESS
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _resolve
for _client in (httpx.Client, httpx.AsyncClient):
    _init = _client.__init__

    def _trusting(self, *args, _init=_init, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("verify", _CONTEXT)
        _init(self, *args, **kwargs)

    _client.__init__ = _trusting  # type: ignore[method-assign]
