from __future__ import annotations

import json
import socketserver
import struct
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from . import registry


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _recv_framed(conn: Any, timeout_s: float = 15.0) -> bytes:
    conn.settimeout(timeout_s)
    header = b""
    while len(header) < 4:
        chunk = conn.recv(4 - len(header))
        if not chunk:
            raise ConnectionError("connection closed while reading header")
        header += chunk
    length = struct.unpack(">I", header)[0]
    if length == 0 or length > 8_388_608:
        raise ValueError(f"invalid frame length: {length}")
    body = b""
    while len(body) < length:
        chunk = conn.recv(length - len(body))
        if not chunk:
            raise ConnectionError("connection closed while reading body")
        body += chunk
    return body


def _send_framed(conn: Any, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn.sendall(struct.pack(">I", len(body)) + body)


class _SessionTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], service: "BrokerSessionsService") -> None:
        super().__init__(address, handler)
        self.service = service


class _SessionRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        service: BrokerSessionsService = self.server.service  # type: ignore[attr-defined]
        conn = self.request
        try:
            raw = _recv_framed(conn, timeout_s=service.recv_timeout_ms / 1000.0)
            request = json.loads(raw.decode("utf-8"))
            if request.get("action") != "broker_sessions_pull":
                _send_framed(conn, {"action": "noop"})
                return

            symbols_to_fetch = registry.get_fetch_request()
            if not symbols_to_fetch:
                _send_framed(conn, {"action": "noop"})
                service._mark_pull()  # noqa: SLF001
                return

            _send_framed(conn, {"action": "fetch_sessions", "symbols": symbols_to_fetch})
            raw_payload = _recv_framed(conn, timeout_s=max(service.recv_timeout_ms / 1000.0, 30.0))
            payload = json.loads(raw_payload.decode("utf-8"))
            sessions = payload.get("sessions", {})
            if not isinstance(sessions, dict) or not sessions:
                _send_framed(conn, {"action": "error", "detail": "empty sessions"})
                service._mark_error("empty or invalid sessions payload")  # noqa: SLF001
                return

            registry.apply_incoming_sessions(sessions)
            generation = str(uuid.uuid4())[:8]
            _send_framed(conn, {"action": "ack", "generation": generation})
            service._mark_pull(generation=generation)  # noqa: SLF001
        except (ConnectionError, struct.error, json.JSONDecodeError, OSError) as exc:
            service._mark_error(f"session handler error: {exc}")  # noqa: SLF001
        except Exception as exc:  # pragma: no cover - defensive
            service._mark_error(f"unexpected session handler error: {exc}")  # noqa: SLF001
            traceback.print_exc()


class BrokerSessionsService:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 5561,
        recv_timeout_ms: int = 15000,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.recv_timeout_ms = int(recv_timeout_ms)
        self._server: _SessionTCPServer | None = None
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._started_at: str = ""
        self._last_pull_at: str = ""
        self._last_error: str = ""
        self._last_generation: str = ""

    def _mark_error(self, message: str) -> None:
        with self._state_lock:
            self._last_error = str(message)

    def _mark_pull(self, *, generation: str = "") -> None:
        with self._state_lock:
            self._last_pull_at = _utc_now_iso()
            if generation:
                self._last_generation = generation
            self._last_error = ""

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running:
            return True
        try:
            server = _SessionTCPServer((self.host, self.port), _SessionRequestHandler, self)
        except Exception as exc:
            self._mark_error(f"failed to start broker sessions service on {self.host}:{self.port}: {exc}")
            return False

        def _serve() -> None:
            try:
                server.serve_forever()
            finally:
                server.server_close()

        thread = threading.Thread(target=_serve, name="broker-sessions-service", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        with self._state_lock:
            self._started_at = _utc_now_iso()
            self._last_error = ""
        return True

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def bootstrap_active_symbols(self, symbols: list[str]) -> None:
        registry.queue_bootstrap(symbols)

    def replace_active_symbols(self, symbols: list[str], *, reason: str = "") -> None:
        normalized_new = {item.upper() for item in symbols if str(item).strip()}
        current = set(registry.get_session_registry().get("active_symbols", []))
        to_add = sorted(normalized_new - current)
        to_remove = sorted(current - normalized_new)
        if to_remove:
            registry.remove_active_symbols(to_remove)
        if to_add:
            registry.add_pending_symbols(to_add)
        if reason:
            self._mark_error(f"universe replaced ({reason}), +{len(to_add)} -{len(to_remove)}")

    def snapshot(self) -> dict[str, Any]:
        state = registry.get_session_registry()
        with self._state_lock:
            return {
                "service": {
                    "running": self.is_running,
                    "host": self.host,
                    "port": self.port,
                    "started_at": self._started_at,
                    "last_pull_at": self._last_pull_at,
                    "last_generation": self._last_generation,
                    "last_error": self._last_error,
                },
                **state,
            }
