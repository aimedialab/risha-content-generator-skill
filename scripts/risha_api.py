#!/usr/bin/env python3
"""Minimal CLI for authenticated Risha API discovery and generation workflows."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from http.cookies import SimpleCookie
from typing import Any
import uuid


DEFAULT_BASE_URL = "https://adminxcore-api.risha.ai/api"
USER_AGENT = "risha-content-generator/0.1"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
TOKEN_KEYS = ("access", "access_token", "token", "jwt")


class RishaClientError(RuntimeError):
    """Raised when the CLI cannot continue safely."""


def merge_nested_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise RishaClientError("Manual field path cannot be empty.")

    cursor = target
    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            existing = {}
            cursor[part] = existing
        elif not isinstance(existing, dict):
            raise RishaClientError(
                f"Cannot merge field path '{path}' because '{part}' already holds a non-object value."
            )
        cursor = existing
    cursor[parts[-1]] = value


def parse_manual_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    buffer = ""
    index = 0

    while index < len(path):
        char = path[index]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            index += 1
            continue
        if char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            closing = path.find("]", index)
            if closing == -1:
                raise RishaClientError(f"Invalid field path '{path}': missing closing bracket.")
            raw_index = path[index + 1 : closing].strip()
            if not raw_index.isdigit():
                raise RishaClientError(f"Invalid field path '{path}': array index must be numeric.")
            tokens.append(int(raw_index))
            index = closing + 1
            continue
        buffer += char
        index += 1

    if buffer:
        tokens.append(buffer)
    return tokens


def get_nested_path(target: Any, path: str) -> Any:
    cursor = target
    for token in parse_manual_path(path):
        if isinstance(token, int):
            if not isinstance(cursor, list) or token >= len(cursor):
                return None
            cursor = cursor[token]
        else:
            if not isinstance(cursor, dict) or token not in cursor:
                return None
            cursor = cursor[token]
    return cursor


def set_nested_path(target: Any, path: str, value: Any) -> None:
    tokens = parse_manual_path(path)
    if not tokens:
        raise RishaClientError("Manual field path cannot be empty.")

    cursor = target
    for current, next_token in zip(tokens, tokens[1:]):
        if isinstance(current, int):
            if not isinstance(cursor, list):
                raise RishaClientError(f"Cannot assign array path '{path}' into a non-list value.")
            while len(cursor) <= current:
                cursor.append({} if isinstance(next_token, str) else [])
            if cursor[current] is None:
                cursor[current] = {} if isinstance(next_token, str) else []
            cursor = cursor[current]
            continue

        if not isinstance(cursor, dict):
            raise RishaClientError(f"Cannot assign object path '{path}' into a non-object value.")
        if current not in cursor or cursor[current] is None:
            cursor[current] = {} if isinstance(next_token, str) else []
        cursor = cursor[current]

    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(cursor, list):
            raise RishaClientError(f"Cannot assign array path '{path}' into a non-list value.")
        while len(cursor) <= last:
            cursor.append(None)
        cursor[last] = value
        return

    if not isinstance(cursor, dict):
        raise RishaClientError(f"Cannot assign object path '{path}' into a non-object value.")
    cursor[last] = value


def json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def parse_field_value(raw_value: str) -> Any:
    stripped = raw_value.strip()
    if not stripped:
        return ""

    json_like_prefixes = ("{", "[", '"')
    if stripped.startswith(json_like_prefixes) or stripped in {"true", "false", "null"}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return raw_value

    if stripped[0] in "-0123456789":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return raw_value

    return raw_value


def write_text_file(path: str, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def infer_file_content_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def looks_like_http_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def looks_like_file_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme == "file"


def looks_like_data_url(value: str) -> bool:
    return value.startswith("data:")


def looks_like_local_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith(("~", "/", "./", "../")):
        return True
    if len(value) >= 3 and value[1:3] == ":\\":
        return True
    return Path(value).exists()


def decode_data_url_to_tempfile(value: str, accepted_file_type: str | None) -> str:
    header, _, data = value.partition(",")
    if not header or not data:
        raise RishaClientError("Invalid data URL provided for file input.")

    mime_type = "application/octet-stream"
    if ":" in header and ";" in header:
        mime_type = header.split(":", 1)[1].split(";", 1)[0] or mime_type
    elif ":" in header:
        mime_type = header.split(":", 1)[1] or mime_type

    try:
        content = base64.b64decode(data)
    except Exception as exc:  # pragma: no cover - defensive
        raise RishaClientError("Could not decode base64 data URL for file input.") from exc

    extension = mimetypes.guess_extension(mime_type) or ""
    if not extension and accepted_file_type == "image":
        extension = ".png"
    elif not extension and accepted_file_type == "audio":
        extension = ".wav"
    elif not extension and accepted_file_type == "video":
        extension = ".mp4"

    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as handle:
        handle.write(content)
        return handle.name


def infer_filename_from_url(url: str, content_type: str, accepted_file_type: str | None) -> str:
    parsed = urllib.parse.urlparse(url)
    candidate = Path(urllib.parse.unquote(parsed.path)).name
    if candidate:
        return candidate

    extension = mimetypes.guess_extension(content_type) or ""
    if not extension and accepted_file_type == "image":
        extension = ".png"
    elif not extension and accepted_file_type == "audio":
        extension = ".wav"
    elif not extension and accepted_file_type == "video":
        extension = ".mp4"
    return f"downloaded-file{extension}"


def download_url_to_tempfile(url: str, accepted_file_type: str | None) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
            filename = infer_filename_from_url(response.geturl() or url, content_type, accepted_file_type)
            suffix = Path(filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(response.read())
                return handle.name
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise RishaClientError(
                f"File input URL requires authentication or is not publicly accessible: {url}"
            ) from exc
        raise RishaClientError(f"Could not download file input URL {url}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RishaClientError(f"Could not download file input URL {url}: {exc.reason}") from exc


def collect_url_candidates(payload: Any, *, seen: set[int] | None = None) -> list[str]:
    if seen is None:
        seen = set()

    results: list[str] = []
    marker = id(payload)
    if marker in seen:
        return results
    seen.add(marker)

    if isinstance(payload, str):
        if looks_like_http_url(payload.strip()):
            results.append(payload.strip())
        return results

    if isinstance(payload, dict):
        for value in payload.values():
            results.extend(collect_url_candidates(value, seen=seen))
        return results

    if isinstance(payload, list):
        for item in payload:
            results.extend(collect_url_candidates(item, seen=seen))
        return results

    return results


def score_asset_url(url: str) -> tuple[int, int]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if host == "adminxcore-api.risha.ai" and "/api/media/asset/" in path:
        return (100, len(url))

    if "/cdn-cgi/image/" in path or "imagedelivery.net" in host or "res.cloudinary.com" in host:
        return (80, len(url))

    if any(token in host for token in ("s3.amazonaws.com", "amazonaws.com", "cloudfront.net", "storage.googleapis.com")):
        return (0, len(url))

    return (10, len(url))


def choose_preferred_public_url(candidates: list[str]) -> str | None:
    normalized = []
    seen = set()
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned and cleaned not in seen and looks_like_http_url(cleaned):
            normalized.append(cleaned)
            seen.add(cleaned)

    if not normalized:
        return None

    best = min(normalized, key=score_asset_url)
    if score_asset_url(best)[0] >= 80:
        return None
    return best


def summarize_choice_field(field: dict[str, Any]) -> str:
    choice_model = field.get("choice_model")
    if not choice_model:
        return ""

    if choice_model == "enum_values":
        values = field.get("enum_values") or []
        labels = []
        for value in values[:6]:
            if isinstance(value, dict):
                label = value.get("label_en") or value.get("label") or value.get("value")
                if label:
                    labels.append(str(label))
            else:
                labels.append(str(value))
        suffix = f" [{', '.join(labels)}]" if labels else ""
        return f"enum_values{suffix}"

    choice_map = {
        "dialects": "dialect_choices",
        "voices": "voice_choices",
        "creators": "creator_choices",
    }
    source_key = choice_map.get(choice_model)
    choices = field.get(source_key) or []
    labels = []
    for choice in choices[:6]:
        if isinstance(choice, dict):
            label = choice.get("display_label_en") or choice.get("display_label") or choice.get("label")
            if label:
                labels.append(str(label))
    suffix = f" [{', '.join(labels)}]" if labels else ""
    return f"{choice_model}{suffix}"


def summarize_field(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": field.get("field_path"),
        "name": field.get("display_name_en") or field.get("display_name") or field.get("field_name"),
        "type": field.get("json_type"),
        "required": bool(field.get("is_required")),
        "file_type": field.get("accepted_file_type"),
        "choice_source": field.get("choice_model"),
        "choice_summary": summarize_choice_field(field),
    }


def build_capability_catalog(capabilities_response: dict[str, Any], base_url: str) -> dict[str, Any]:
    results = capabilities_response.get("results", [])
    category_counts: dict[str, int] = {}
    catalog_items = []

    for item in results:
        category = item.get("category") or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1

        manual = item.get("manual") or {}
        fields = manual.get("fields") or []
        input_fields = [field for field in fields if field.get("field_type") == "input"]
        output_fields = [field for field in fields if field.get("field_type") == "output"]
        required_inputs = [field.get("field_path") for field in input_fields if field.get("is_required")]

        catalog_items.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "display_name": item.get("display_name"),
                "category": category,
                "credit_cost": item.get("credit_cost"),
                "supports_async": bool(manual.get("supports_async")),
                "output_media_type": manual.get("output_media_type"),
                "required_inputs": required_inputs,
                "input_fields": [summarize_field(field) for field in input_fields],
                "output_fields": [summarize_field(field) for field in output_fields],
                "input_schema": manual.get("input_schema"),
                "output_schema": manual.get("output_schema"),
                "manual": manual,
            }
        )

    return {
        "base_url": base_url,
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": capabilities_response.get("count", len(results)),
        "category_counts": category_counts,
        "capabilities": catalog_items,
    }


def render_catalog_markdown(catalog: dict[str, Any]) -> str:
    lines = [
        "# Current Risha Capabilities",
        "",
        f"- Refreshed at: `{catalog['refreshed_at']}`",
        f"- Base URL: `{catalog['base_url']}`",
        f"- Capability count: `{catalog['count']}`",
        "",
        "## Categories",
        "",
    ]

    for category, count in sorted(catalog["category_counts"].items()):
        lines.append(f"- `{category}`: {count}")

    lines.extend(["", "## Capability Inventory", ""])

    for capability in sorted(catalog["capabilities"], key=lambda item: (item["category"], item["id"])):
        lines.append(
            f"### {capability['display_name']} (`{capability['id']}`)"
        )
        lines.append("")
        lines.append(f"- Internal name: `{capability['name']}`")
        lines.append(f"- Category: `{capability['category']}`")
        lines.append(f"- Output type: `{capability['output_media_type']}`")
        lines.append(f"- Supports async: `{str(capability['supports_async']).lower()}`")
        lines.append(f"- Base credit cost: `{capability['credit_cost']}`")
        required_inputs = capability.get("required_inputs") or []
        lines.append(
            f"- Required inputs: `{', '.join(required_inputs)}`" if required_inputs else "- Required inputs: none"
        )
        lines.append("- Inputs:")
        if capability["input_fields"]:
            for field in capability["input_fields"]:
                detail = f"`{field['path']}` ({field['type']})"
                if field["required"]:
                    detail += " required"
                if field.get("file_type"):
                    detail += f", file={field['file_type']}"
                if field.get("choice_summary"):
                    detail += f", choices={field['choice_summary']}"
                lines.append(f"  - {detail}")
        else:
            lines.append("  - none")
        lines.append("- Outputs:")
        if capability["output_fields"]:
            for field in capability["output_fields"]:
                detail = f"`{field['path']}` ({field['type']})"
                lines.append(f"  - {detail}")
        else:
            lines.append("  - none")
        lines.append("")

    return "\n".join(lines) + "\n"


class RishaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("RISHA_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.cookie_jar: dict[str, str] = {}
        self.session_header: str | None = None
        self.last_login_payload: dict[str, Any] | None = None

    def get_auth_header(self) -> str | None:
        env_header = os.environ.get("RISHA_AUTH_HEADER")
        if env_header:
            return env_header.strip()

        if self.session_header:
            return self.session_header

        username = os.environ.get("RISHA_BASIC_USERNAME")
        password = os.environ.get("RISHA_BASIC_PASSWORD")
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            return f"Basic {token}"

        return None

    def login(self) -> dict[str, Any]:
        email = os.environ.get("RISHA_EMAIL")
        password = os.environ.get("RISHA_PASSWORD")
        if not email or not password:
            raise RishaClientError(
                "Set RISHA_AUTH_HEADER or both RISHA_EMAIL and RISHA_PASSWORD before calling authenticated endpoints."
            )

        payload = {"email": email, "password": password}
        response = self.request("POST", "/auth/login/", payload=payload, allow_missing_auth=True)
        self.last_login_payload = response
        self._extract_session_header(response)
        return response

    def ensure_authenticated(self) -> None:
        if self.get_auth_header() or self.cookie_jar:
            return
        self.login()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
        allow_missing_auth: bool = False,
    ) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        data: bytes | None = None
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        auth_header = self.get_auth_header()
        if auth_header:
            headers["Authorization"] = auth_header

        if self.cookie_jar:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookie_jar.items())

        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read().decode("utf-8")
                self._capture_cookies(response.headers)
                return self._decode_json(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self._capture_cookies(exc.headers)
            parsed = self._try_decode_json(body)
            if exc.code == 401 and not allow_missing_auth:
                if not auth_header and not self.cookie_jar:
                    self.login()
                    return self.request(
                        method,
                        path,
                        params=params,
                        payload=payload,
                        allow_missing_auth=True,
                    )
            raise RishaClientError(
                f"{method.upper()} {path} failed with HTTP {exc.code}: {json_dump(parsed) if parsed is not None else body}"
            ) from exc

    def request_multipart(
        self,
        method: str,
        path: str,
        *,
        form_fields: dict[str, str] | None = None,
        file_fields: dict[str, tuple[str, bytes, str]] | None = None,
        params: dict[str, Any] | None = None,
        allow_missing_auth: bool = False,
    ) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        boundary = f"----RishaBoundary{uuid.uuid4().hex}"
        body = bytearray()

        for name, value in (form_fields or {}).items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
            )

        for name, (filename, content, content_type) in (file_fields or {}).items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
            )
            body.extend(content)
            body.extend(b"\r\n")

        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": USER_AGENT,
        }

        auth_header = self.get_auth_header()
        if auth_header:
            headers["Authorization"] = auth_header

        if self.cookie_jar:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookie_jar.items())

        request = urllib.request.Request(url, data=bytes(body), method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                payload = response.read().decode("utf-8")
                self._capture_cookies(response.headers)
                return self._decode_json(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            self._capture_cookies(exc.headers)
            parsed = self._try_decode_json(payload)
            if exc.code == 401 and not allow_missing_auth:
                if not auth_header and not self.cookie_jar:
                    self.login()
                    return self.request_multipart(
                        method,
                        path,
                        form_fields=form_fields,
                        file_fields=file_fields,
                        params=params,
                        allow_missing_auth=True,
                    )
            raise RishaClientError(
                f"{method.upper()} {path} failed with HTTP {exc.code}: {json_dump(parsed) if parsed is not None else payload}"
            ) from exc

    def _capture_cookies(self, headers: Any) -> None:
        for header in headers.get_all("Set-Cookie", []):
            cookie = SimpleCookie()
            cookie.load(header)
            for name, morsel in cookie.items():
                self.cookie_jar[name] = morsel.value

    def _extract_session_header(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return

        token = self._find_token(payload)
        if token:
            self.session_header = f"Bearer {token}"

    def _find_token(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in TOKEN_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                token = self._find_token(value)
                if token:
                    return token
        elif isinstance(payload, list):
            for item in payload:
                token = self._find_token(item)
                if token:
                    return token
        return None

    def _decode_json(self, body: str) -> Any:
        parsed = self._try_decode_json(body)
        if parsed is None:
            raise RishaClientError(f"Expected JSON response but received: {body[:500]}")
        return parsed

    @staticmethod
    def _try_decode_json(body: str) -> Any | None:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None


def get_wallet_summary(client: RishaClient) -> dict[str, Any]:
    for endpoint in ("/credits/wallets/my-wallet/", "/credits/wallets/my-summary/"):
        payload = client.request("GET", endpoint)
        if isinstance(payload, dict):
            results = payload.get("results")
            if isinstance(results, list) and results:
                return results[0]
            if "available_credits" in payload or "total_credits" in payload:
                return payload
    raise RishaClientError("Wallet summary response did not include a recognized wallet shape.")


def estimate_credit_cost(client: RishaClient, capability_id: int, prompt_data: dict[str, Any]) -> dict[str, Any]:
    payload = client.request(
        "POST",
        f"/customer/capabilities/{capability_id}/calculate-credit-cost/",
        payload={"prompt_data": prompt_data},
    )
    if not isinstance(payload, dict):
        raise RishaClientError("Credit cost estimate response was not a JSON object.")
    return payload


def build_credit_preview(client: RishaClient, capability_id: int, prompt_data: dict[str, Any]) -> dict[str, Any]:
    wallet = get_wallet_summary(client)
    estimate = estimate_credit_cost(client, capability_id, prompt_data)
    available = coerce_number(wallet.get("available_credits"))
    total_cost = coerce_number(estimate.get("total_cost"))

    projected_remaining = None
    if available is not None and total_cost is not None:
        projected_remaining = available - total_cost

    return {
        "wallet": {
            "available_credits": wallet.get("available_credits"),
            "allocated_credits": wallet.get("allocated_credits"),
            "total_credits": wallet.get("total_credits"),
            "total_used_credits": wallet.get("total_used_credits"),
            "credits_expiring_soon": wallet.get("credits_expiring_soon"),
            "next_expiry_date": wallet.get("next_expiry_date"),
        },
        "estimate": estimate,
        "projected_remaining_credits": projected_remaining,
        "has_enough_credits": None if projected_remaining is None else projected_remaining >= 0,
    }


def upload_asset(
    client: RishaClient,
    file_path: str,
    *,
    display_name: str | None = None,
    source: str = "uploaded",
) -> dict[str, Any]:
    path_obj = Path(file_path)
    if not path_obj.is_file():
        raise RishaClientError(f"Asset file does not exist: {file_path}")

    content = path_obj.read_bytes()
    filename = path_obj.name
    response = client.request_multipart(
        "POST",
        "/assets/",
        form_fields={
            "file_name": display_name or filename,
            "source": source,
        },
        file_fields={
            "file": (
                filename,
                content,
                infer_file_content_type(str(path_obj)),
            )
        },
    )
    if not isinstance(response, dict):
        raise RishaClientError("Asset upload response was not a JSON object.")
    return response


def extract_asset_file_url(payload: dict[str, Any]) -> str | None:
    candidates = collect_url_candidates(payload)
    return choose_preferred_public_url(candidates)


def normalize_file_field_value(client: RishaClient, value: Any, *, accepted_file_type: str | None, field_path: str) -> str:
    if not isinstance(value, str):
        raise RishaClientError(f"File field '{field_path}' must be a string path, URL, or data URL.")

    stripped = value.strip()
    if not stripped:
        raise RishaClientError(f"File field '{field_path}' cannot be empty.")

    temp_paths: list[str] = []
    try:
        if looks_like_data_url(stripped):
            upload_path = decode_data_url_to_tempfile(stripped, accepted_file_type)
            temp_paths.append(upload_path)
        elif looks_like_http_url(stripped):
            upload_path = download_url_to_tempfile(stripped, accepted_file_type)
            temp_paths.append(upload_path)
        elif looks_like_file_url(stripped):
            upload_path = urllib.request.url2pathname(urllib.parse.urlparse(stripped).path)
        elif looks_like_local_path(stripped):
            upload_path = str(Path(stripped).expanduser().resolve())
        else:
            raise RishaClientError(
                f"File field '{field_path}' must be a local file path, file:// URL, data URL, or publicly downloadable http(s) URL."
            )

        asset_payload = upload_asset(client, upload_path, source="input_normalized")
        file_url = extract_asset_file_url(asset_payload)
        if not file_url:
            candidates = collect_url_candidates(asset_payload)
            raise RishaClientError(
                f"Asset upload for file field '{field_path}' did not return a usable public URL. "
                f"Candidates seen: {candidates if candidates else 'none'}"
            )
        return file_url
    finally:
        for temp_path in temp_paths:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def normalize_prompt_data_files(client: RishaClient, capability_id: int, prompt_data: dict[str, Any]) -> dict[str, Any]:
    capability = client.request("GET", f"/customer/capabilities/{capability_id}/")
    if not isinstance(capability, dict):
        raise RishaClientError("Capability detail response was not a JSON object.")

    manual = capability.get("manual") or {}
    fields = manual.get("fields") or []
    normalized = deepcopy(prompt_data)

    for field in fields:
        if field.get("field_type") != "input":
            continue
        if field.get("json_type") != "file" and not field.get("accepted_file_type"):
            continue

        field_path = field.get("field_path")
        if not isinstance(field_path, str) or not field_path:
            continue

        current_value = get_nested_path(normalized, field_path)
        if current_value in (None, ""):
            continue

        normalized_value = normalize_file_field_value(
            client,
            current_value,
            accepted_file_type=field.get("accepted_file_type"),
            field_path=field_path,
        )
        set_nested_path(normalized, field_path, normalized_value)

    return normalized


def add_common_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", help="Override RISHA_API_BASE_URL for this command.")


def command_login(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    payload = client.login()
    result = {
        "login_response": payload,
        "derived_authorization_header": client.session_header,
        "cookies": deepcopy(client.cookie_jar),
    }
    print(json_dump(result))
    return 0


def command_me(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    print(json_dump(client.request("GET", "/auth/me/")))
    return 0


def command_wallet(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    print(json_dump(get_wallet_summary(client)))
    return 0


def command_capabilities(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    params = {
        "category": args.category,
        "search": args.search,
        "page_size": args.page_size,
    }
    print(json_dump(client.request("GET", "/customer/capabilities/", params=params)))
    return 0


def command_capability(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    print(json_dump(client.request("GET", f"/customer/capabilities/{args.capability_id}/")))
    return 0


def command_creators(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    params = {
        "category": args.category,
        "search": args.search,
    }
    print(json_dump(client.request("GET", "/customer/capabilities/creator-choices/", params=params)))
    return 0


def fetch_all_capabilities(client: RishaClient, *, category: str | None, search: str | None, page_size: int) -> dict[str, Any]:
    page = 1
    results: list[dict[str, Any]] = []
    total_count: int | None = None

    while True:
        params = {
            "category": category,
            "search": search,
            "page_size": page_size,
            "page": page,
        }
        payload = client.request("GET", "/customer/capabilities/", params=params)
        if total_count is None:
            total_count = payload.get("count", 0)
        results.extend(payload.get("results", []))
        if not payload.get("next"):
            break
        page += 1

    return {
        "count": total_count if total_count is not None else len(results),
        "results": results,
    }


def command_catalog(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    capabilities_response = fetch_all_capabilities(
        client,
        category=args.category,
        search=args.search,
        page_size=args.page_size,
    )
    catalog = build_capability_catalog(capabilities_response, client.base_url)
    output = json_dump(catalog)
    if args.write_json:
        write_text_file(args.write_json, output + "\n")
    if args.write_markdown:
        write_text_file(args.write_markdown, render_catalog_markdown(catalog))
    if args.quiet:
        summary = {
            "count": catalog["count"],
            "category_counts": catalog["category_counts"],
            "capabilities": [
                {
                    "id": capability["id"],
                    "display_name": capability["display_name"],
                    "category": capability["category"],
                }
                for capability in catalog["capabilities"]
            ],
        }
        print(json_dump(summary))
    else:
        print(output)
    return 0


def load_prompt_data_from_args(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    if args.prompt_data:
        raw = json.loads(args.prompt_data)
        if not isinstance(raw, dict):
            raise RishaClientError("--prompt-data must decode to a JSON object.")
        payload = raw

    if args.prompt_data_file:
        with open(args.prompt_data_file, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise RishaClientError("--prompt-data-file must contain a JSON object.")
        payload = raw

    for assignment in args.field:
        if "=" not in assignment:
            raise RishaClientError(f"Invalid --field '{assignment}'. Use dotted.path=value.")
        path, raw_value = assignment.split("=", 1)
        value = parse_field_value(raw_value)
        merge_nested_path(payload, path, value)

    if not payload:
        raise RishaClientError(
            "Provide --prompt-data, --prompt-data-file, or one or more --field values to build prompt_data."
        )

    return payload


def print_generation_summary(record: dict[str, Any]) -> None:
    summary = {
        "id": record.get("id"),
        "title": record.get("title"),
        "status": record.get("status"),
        "capability_name": record.get("capability_name"),
        "error_message": record.get("error_message"),
        "generated_content": record.get("generated_content"),
    }
    print(json_dump(summary))


def wait_for_generation(
    client: RishaClient,
    request_id: int,
    *,
    poll_interval: float,
    max_attempts: int,
) -> dict[str, Any]:
    attempt = 0
    latest: dict[str, Any] | None = None
    while attempt < max_attempts:
        attempt += 1
        latest = client.request("GET", f"/generation-requests/{request_id}/")
        status = latest.get("status")
        if status in TERMINAL_STATUSES:
            return latest
        time.sleep(poll_interval)
    raise RishaClientError(
        f"Generation request {request_id} did not reach a terminal state after {max_attempts} polling attempts."
    )


def command_generate(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    prompt_data = normalize_prompt_data_files(
        client,
        args.capability_id,
        load_prompt_data_from_args(args),
    )
    credit_preview = build_credit_preview(client, args.capability_id, prompt_data)
    request_payload = {
        "capability": args.capability_id,
        "title": args.title,
        "prompt_data": prompt_data,
    }
    request_payload = {key: value for key, value in request_payload.items() if value is not None}
    created = client.request("POST", "/generation-requests/", payload=request_payload)

    if args.wait:
        request_id = created.get("id")
        if not isinstance(request_id, int):
            raise RishaClientError(
                "Generation request was created but the response did not include an integer 'id'."
            )
        completed = wait_for_generation(
            client,
            request_id,
            poll_interval=args.poll_interval,
            max_attempts=args.max_attempts,
        )
        summary = {
            "credit_preview": credit_preview,
            "generation": {
                "id": completed.get("id"),
                "title": completed.get("title"),
                "status": completed.get("status"),
                "capability_name": completed.get("capability_name"),
                "error_message": completed.get("error_message"),
                "generated_content": completed.get("generated_content"),
            },
        }
        print(json_dump(summary))
        return 0 if completed.get("status") == "completed" else 2

    print(
        json_dump(
            {
                "credit_preview": credit_preview,
                "generation_request": created,
            }
        )
    )
    return 0


def command_estimate(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    prompt_data = normalize_prompt_data_files(
        client,
        args.capability_id,
        load_prompt_data_from_args(args),
    )
    print(json_dump(build_credit_preview(client, args.capability_id, prompt_data)))
    return 0


def command_generation(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    print(json_dump(client.request("GET", f"/generation-requests/{args.request_id}/")))
    return 0


def command_generated_content(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    print(json_dump(client.request("GET", f"/generation-requests/{args.request_id}/generated_content/")))
    return 0


def command_upload_asset(args: argparse.Namespace) -> int:
    client = RishaClient(base_url=args.base_url)
    client.ensure_authenticated()
    response = upload_asset(
        client,
        args.file_path,
        display_name=args.display_name,
        source=args.source,
    )
    print(
        json_dump(
            {
                "asset": response,
                "public_url": extract_asset_file_url(response),
            }
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and use the Risha API.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Log in with RISHA_EMAIL and RISHA_PASSWORD.")
    add_common_auth_args(login_parser)
    login_parser.set_defaults(func=command_login)

    me_parser = subparsers.add_parser("me", help="Fetch the authenticated user profile.")
    add_common_auth_args(me_parser)
    me_parser.set_defaults(func=command_me)

    wallet_parser = subparsers.add_parser("wallet", help="Fetch the current credit wallet summary.")
    add_common_auth_args(wallet_parser)
    wallet_parser.set_defaults(func=command_wallet)

    capabilities_parser = subparsers.add_parser("capabilities", help="List customer capabilities.")
    add_common_auth_args(capabilities_parser)
    capabilities_parser.add_argument("--category", help="Filter capabilities by category.")
    capabilities_parser.add_argument("--search", help="Search capabilities by text.")
    capabilities_parser.add_argument("--page-size", type=int, default=50, help="Number of items per page.")
    capabilities_parser.set_defaults(func=command_capabilities)

    catalog_parser = subparsers.add_parser(
        "catalog",
        help="Fetch all accessible capabilities and optionally write a reusable catalog snapshot.",
    )
    add_common_auth_args(catalog_parser)
    catalog_parser.add_argument("--category", help="Optional category filter.")
    catalog_parser.add_argument("--search", help="Optional text filter.")
    catalog_parser.add_argument("--page-size", type=int, default=100, help="Number of items per page.")
    catalog_parser.add_argument("--write-json", help="Write the catalog JSON to this path.")
    catalog_parser.add_argument("--write-markdown", help="Write a Markdown summary to this path.")
    catalog_parser.add_argument("--quiet", action="store_true", help="Print only a concise summary after refresh.")
    catalog_parser.set_defaults(func=command_catalog)

    capability_parser = subparsers.add_parser("capability", help="Fetch a single capability detail.")
    add_common_auth_args(capability_parser)
    capability_parser.add_argument("capability_id", type=int, help="Capability ID.")
    capability_parser.set_defaults(func=command_capability)

    creators_parser = subparsers.add_parser("creators", help="List creator choices.")
    add_common_auth_args(creators_parser)
    creators_parser.add_argument("--category", default="text_generation", help="Optional category filter.")
    creators_parser.add_argument("--search", help="Search creator choices.")
    creators_parser.set_defaults(func=command_creators)

    upload_asset_parser = subparsers.add_parser(
        "upload-asset",
        help="Upload a local media file to Risha assets and return the created asset record.",
    )
    add_common_auth_args(upload_asset_parser)
    upload_asset_parser.add_argument("file_path", help="Local file path to upload.")
    upload_asset_parser.add_argument("--display-name", help="Optional asset display name.")
    upload_asset_parser.add_argument(
        "--source",
        default="uploaded",
        help="Asset source value. Defaults to uploaded.",
    )
    upload_asset_parser.set_defaults(func=command_upload_asset)

    estimate_parser = subparsers.add_parser(
        "estimate",
        help="Estimate credit cost and remaining balance without creating a generation request.",
    )
    add_common_auth_args(estimate_parser)
    estimate_parser.add_argument("--capability-id", type=int, required=True, help="Capability ID to estimate.")
    estimate_parser.add_argument("--prompt-data", help="Inline JSON object for prompt_data.")
    estimate_parser.add_argument("--prompt-data-file", help="Path to a JSON file containing prompt_data.")
    estimate_parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Set a dotted manual path such as input.text='hello'. Can be used multiple times.",
    )
    estimate_parser.set_defaults(func=command_estimate)

    generate_parser = subparsers.add_parser("generate", help="Create a generation request.")
    add_common_auth_args(generate_parser)
    generate_parser.add_argument("--capability-id", type=int, required=True, help="Capability ID to invoke.")
    generate_parser.add_argument("--title", help="Optional generation title.")
    generate_parser.add_argument("--prompt-data", help="Inline JSON object for prompt_data.")
    generate_parser.add_argument("--prompt-data-file", help="Path to a JSON file containing prompt_data.")
    generate_parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Set a dotted manual path such as input.text='hello'. Can be used multiple times.",
    )
    generate_parser.add_argument("--wait", action="store_true", help="Poll until the request finishes.")
    generate_parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between polls when --wait is used.",
    )
    generate_parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Maximum number of polls when --wait is used.",
    )
    generate_parser.set_defaults(func=command_generate)

    generation_parser = subparsers.add_parser("generation", help="Fetch a generation request by ID.")
    add_common_auth_args(generation_parser)
    generation_parser.add_argument("request_id", type=int, help="Generation request ID.")
    generation_parser.set_defaults(func=command_generation)

    generated_content_parser = subparsers.add_parser(
        "generated-content",
        help="Fetch generated content via the request-specific endpoint.",
    )
    add_common_auth_args(generated_content_parser)
    generated_content_parser.add_argument("request_id", type=int, help="Generation request ID.")
    generated_content_parser.set_defaults(func=command_generated_content)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (RishaClientError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
