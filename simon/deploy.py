"""Compile `agents/<name>/` packages and deploy them to Gemini `/v1beta/agents`."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AGENTS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/agents"
CREDENTIALS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/credentials"
DEFAULT_API_REVISION = "2026-05-20"
MAX_INLINE_FILE_BYTES = 1_000_000
MAX_INLINE_TOTAL_BYTES = 2_000_000

# Reserved prefixes rejected by POST /v1beta/agents
RESERVED_AGENT_PREFIXES = (
    "antigravity-",
    "veo-",
    "omni-",
    "lyria-",
    "imagen-",
    "gemma-",
    "gemini-",
    "google-",
    "youtube-",
    "android-",
    "chrome-",
    "pixel-",
    "waze-",
    "fitbit-",
    "nest-",
    "kaggle-",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_agents_dir() -> Path:
    return repo_root() / "agents"


def _parse_yaml_scalar(raw: str) -> Any:
    val = raw.strip()
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none", "~"):
        return None
    if val == "[]":
        return []
    if val == "{}":
        return {}
    try:
        return int(val)
    except ValueError:
        pass
    return val


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Minimal stdlib YAML parser supporting indented dicts and lists used in agent.yaml."""
    raw_lines: List[Tuple[int, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        raw_lines.append((indent, stripped))

    def parse_block(idx: int, min_indent: int) -> Tuple[Any, int]:
        if idx >= len(raw_lines):
            return {}, idx
        indent, content = raw_lines[idx]
        if content.startswith("- "):
            items: List[Any] = []
            while idx < len(raw_lines):
                cur_indent, cur_text = raw_lines[idx]
                if cur_indent < min_indent or not cur_text.startswith("- "):
                    break
                if cur_indent != indent:
                    break
                rest = cur_text[2:].strip()
                if ":" in rest:
                    key, _, val = rest.partition(":")
                    item_dict: Dict[str, Any] = {key.strip(): _parse_yaml_scalar(val)}
                    idx += 1
                    while idx < len(raw_lines) and raw_lines[idx][0] > cur_indent:
                        sub_indent, sub_text = raw_lines[idx]
                        sk, _, sv = sub_text.partition(":")
                        if sv.strip():
                            item_dict[sk.strip()] = _parse_yaml_scalar(sv)
                            idx += 1
                        else:
                            nested, idx = parse_block(idx + 1, sub_indent + 1)
                            item_dict[sk.strip()] = nested
                    items.append(item_dict)
                else:
                    items.append(_parse_yaml_scalar(rest))
                    idx += 1
            return items, idx

        mapping: Dict[str, Any] = {}
        while idx < len(raw_lines):
            cur_indent, cur_text = raw_lines[idx]
            if cur_indent < min_indent or cur_text.startswith("- "):
                break
            key, _, val = cur_text.partition(":")
            key = key.strip()
            if val.strip():
                mapping[key] = _parse_yaml_scalar(val)
                idx += 1
            else:
                nested, idx = parse_block(idx + 1, cur_indent + 1)
                mapping[key] = nested
        return mapping, idx

    parsed, _ = parse_block(0, 0)
    if not isinstance(parsed, dict):
        raise ValueError("YAML root must be a mapping.")
    return parsed


def _load_spec_file(agent_dir: Path) -> Tuple[Dict[str, Any], Path]:
    json_path = agent_dir / "agent.json"
    yaml_path = agent_dir / "agent.yaml"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8")), json_path
    if yaml_path.exists():
        raw_text = yaml_path.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            loaded = yaml.safe_load(raw_text)
        except ImportError:
            loaded = _parse_simple_yaml(raw_text)
        if not isinstance(loaded, dict):
            raise ValueError(f"{yaml_path} must contain a mapping.")
        return loaded, yaml_path
    raise FileNotFoundError(f"No agent.json or agent.yaml found in {agent_dir}")


def list_agent_packages(agents_dir: Optional[Path] = None) -> List[Path]:
    root = agents_dir or default_agents_dir()
    if not root.exists():
        return []
    packages: List[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name.startswith("_"):
            continue
        if (child / "agent.json").exists() or (child / "agent.yaml").exists():
            packages.append(child)
    return packages


def validate_agent_id(agent_id: str) -> str:
    cleaned = agent_id.strip()
    if not cleaned:
        raise ValueError("Agent ID must be a non-empty string.")
    lower = cleaned.lower()
    for prefix in RESERVED_AGENT_PREFIXES:
        if lower.startswith(prefix):
            raise ValueError(
                f"Agent ID '{cleaned}' cannot start with reserved prefix '{prefix}'."
            )
    return cleaned


def _collect_inline_sources(agent_dir: Path, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen_targets = set()
    total_bytes = 0

    def add_inline(target: str, content: str) -> None:
        nonlocal total_bytes
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_INLINE_FILE_BYTES:
            raise ValueError(
                f"Inline mount '{target}' exceeds 1 MB limit ({len(encoded)} bytes)."
            )
        total_bytes += len(encoded)
        if total_bytes > MAX_INLINE_TOTAL_BYTES:
            raise ValueError(
                f"Total inline mounts in {agent_dir.name} exceed 2 MB limit ({total_bytes} bytes)."
            )
        if target in seen_targets:
            return
        seen_targets.add(target)
        sources.append({"type": "inline", "target": target, "content": content})

    # 1. Always mount SYSTEM.md (or system_instruction_file) as .agents/AGENTS.md if present
    instr_rel = spec.get("system_instruction_file") or "SYSTEM.md"
    instr_path = agent_dir / instr_rel
    if instr_path.is_file():
        add_inline(".agents/AGENTS.md", instr_path.read_text(encoding="utf-8"))

    # 2. Explicit inline_mounts from environment/base_environment
    env_spec = spec.get("base_environment") or spec.get("environment") or {}
    if isinstance(env_spec, dict):
        for mount in env_spec.get("inline_mounts") or []:
            src_file = mount.get("source")
            target = mount.get("target")
            if src_file and target:
                file_path = agent_dir / src_file
                if not file_path.is_file():
                    raise FileNotFoundError(f"Inline mount source not found: {file_path}")
                add_inline(str(target), file_path.read_text(encoding="utf-8"))

        # Preserve any pre-declared sources (repository, gcs, inline, skill_registry)
        for src in env_spec.get("sources") or []:
            if isinstance(src, dict):
                if src.get("type") == "inline" and src.get("target"):
                    add_inline(str(src["target"]), str(src.get("content", "")))
                else:
                    sources.append(dict(src))

        # Optional mount_repo shorthand
        mount_repo = env_spec.get("mount_repo")
        if isinstance(mount_repo, dict) and mount_repo.get("source"):
            sources.append(
                {
                    "type": "repository",
                    "source": str(mount_repo["source"]),
                    "target": str(mount_repo.get("target", "/workspace/repo")),
                }
            )

    # 3. Auto-bundle any files under agents/<name>/skills/** -> .agents/skills/**
    skills_dir = agent_dir / "skills"
    if skills_dir.is_dir():
        for file_path in sorted(skills_dir.rglob("*")):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if "__pycache__" in file_path.parts or file_path.suffix in (".pyc", ".pyo"):
                continue
            rel = file_path.relative_to(skills_dir).as_posix()
            add_inline(f".agents/skills/{rel}", file_path.read_text(encoding="utf-8"))

    # 4. Bundle declared shared_skills from agents/_shared/skills/<skill>/** -> .agents/skills/<skill>/**
    shared_root = agent_dir.parent / "_shared" / "skills"
    for skill_name in spec.get("shared_skills") or []:
        skill_dir = shared_root / str(skill_name)
        if not skill_dir.is_dir():
            raise FileNotFoundError(f"Shared skill '{skill_name}' not found at {skill_dir}")
        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if "__pycache__" in file_path.parts or file_path.suffix in (".pyc", ".pyo"):
                continue
            rel = file_path.relative_to(skill_dir).as_posix()
            add_inline(f".agents/skills/{skill_name}/{rel}", file_path.read_text(encoding="utf-8"))

    return sources


def compile_agent_package(
    agent_dir: Path,
    prefix: str = "",
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Compile an `agents/<name>/` directory into a valid POST /v1beta/agents payload."""
    spec, spec_path = _load_spec_file(agent_dir)

    raw_id = str(spec.get("id") or f"simon-{agent_dir.name}").strip()
    deployed_id = validate_agent_id(f"{prefix}{raw_id}" if prefix else raw_id)

    base_agent = str(spec.get("base_agent") or "antigravity-preview-09-2026").strip()
    agent_config = dict(spec.get("agent_config") or {"type": "antigravity"})
    if model_override:
        agent_config["model"] = model_override

    # Resolve system_instruction from file or inline string
    system_instruction = str(spec.get("system_instruction") or "").strip()
    instr_rel = spec.get("system_instruction_file") or "SYSTEM.md"
    instr_path = agent_dir / instr_rel
    if not system_instruction and instr_path.is_file():
        system_instruction = instr_path.read_text(encoding="utf-8").strip()

    # Build base_environment
    raw_env = spec.get("base_environment") or spec.get("environment") or {"type": "remote"}
    if isinstance(raw_env, str):
        base_environment: Any = raw_env
    else:
        base_environment = {"type": str(raw_env.get("type") or "remote")}
        sources = _collect_inline_sources(agent_dir, spec)
        if sources:
            base_environment["sources"] = sources
        if "network" in raw_env:
            base_environment["network"] = raw_env["network"]
        if "env" in raw_env and isinstance(raw_env["env"], dict):
            base_environment["env"] = raw_env["env"]

    payload: Dict[str, Any] = {
        "id": deployed_id,
        "base_agent": base_agent,
        "agent_config": agent_config,
        "base_environment": base_environment,
    }
    if spec.get("description"):
        payload["description"] = str(spec["description"]).strip()
    if system_instruction:
        payload["system_instruction"] = system_instruction
    if "tools" in spec and spec["tools"] is not None:
        payload["tools"] = list(spec["tools"])

    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:12]

    return {
        "package": agent_dir.name,
        "spec_file": str(spec_path),
        "deployed_id": deployed_id,
        "sha256": digest,
        "payload": payload,
    }


def _api_request(
    method: str,
    url: str,
    api_key: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Tuple[int, Dict[str, Any]]:
    headers = {
        "Api-Revision": DEFAULT_API_REVISION,
        "x-goog-api-key": api_key,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8").strip()
            return resp.status, (json.loads(raw) if raw else {})
    except HTTPError as exc:
        with exc:
            raw = exc.read().decode("utf-8", errors="replace").strip()
            try:
                err_obj = json.loads(raw) if raw else {}
            except ValueError:
                err_obj = {"message": raw or str(exc.reason)}
        return exc.code, err_obj
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Request to {url} failed: {exc}") from None


def deploy_compiled_agent(
    compiled: Dict[str, Any],
    api_key: Optional[str] = None,
    dry_run: bool = False,
    recreate: bool = True,
    out_dir: Optional[Path] = None,
    request_fn=_api_request,
) -> Dict[str, Any]:
    """Deploy a compiled agent package to POST /v1beta/agents (with optional delete+create)."""
    payload = compiled["payload"]
    agent_id = compiled["deployed_id"]

    written_path: Optional[str] = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{compiled['package']}.json"
        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written_path = str(out_file)

    if dry_run:
        return {
            "package": compiled["package"],
            "agent_id": agent_id,
            "sha256": compiled["sha256"],
            "action": "dry_run",
            "status": "ok",
            "written_file": written_path,
            "payload": payload,
        }

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_key:
        raise ValueError("Set GEMINI_API_KEY (or pass --dry-run) before deploying agents.")

    # Check if agent already exists
    status_get, _ = request_fn("GET", f"{AGENTS_ENDPOINT}/{agent_id}", resolved_key)
    action = "created"
    if status_get == 200:
        if not recreate:
            return {
                "package": compiled["package"],
                "agent_id": agent_id,
                "sha256": compiled["sha256"],
                "action": "skipped_existing",
                "status": "ok",
                "written_file": written_path,
            }
        status_del, del_body = request_fn("DELETE", f"{AGENTS_ENDPOINT}/{agent_id}", resolved_key)
        if status_del not in (200, 204):
            raise RuntimeError(f"Failed deleting existing agent '{agent_id}' (HTTP {status_del}): {del_body}")
        action = "recreated"
    elif status_get != 404:
        raise RuntimeError(f"Unexpected HTTP {status_get} checking agent '{agent_id}'.")

    status_post, post_body = request_fn("POST", AGENTS_ENDPOINT, resolved_key, body=payload)
    if status_post not in (200, 201):
        raise RuntimeError(f"Failed creating agent '{agent_id}' (HTTP {status_post}): {post_body}")

    return {
        "package": compiled["package"],
        "agent_id": agent_id,
        "sha256": compiled["sha256"],
        "action": action,
        "status": "ok",
        "written_file": written_path,
        "remote": post_body,
    }


def sync_env_credential(
    credential_id: str,
    value: str,
    trusted_domains: List[str],
    api_key: Optional[str] = None,
    dry_run: bool = False,
    request_fn=_api_request,
) -> Dict[str, Any]:
    """Upsert an environment_variable credential on /v1beta/credentials (write-only secret)."""
    if not credential_id.strip():
        raise ValueError("credential_id must be non-empty.")
    if not value:
        raise ValueError("Credential value must be non-empty.")

    payload = {
        "id": credential_id.strip(),
        "type": "environment_variable",
        "injection_location": "header",
        "trusted_domains": list(trusted_domains),
        "value": value,
    }
    if dry_run:
        return {
            "credential_id": credential_id.strip(),
            "trusted_domains": list(trusted_domains),
            "action": "dry_run",
            "status": "ok",
        }

    resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_key:
        raise ValueError("Set GEMINI_API_KEY before syncing credentials.")

    cid = credential_id.strip()
    status_get, _ = request_fn("GET", f"{CREDENTIALS_ENDPOINT}/{cid}", resolved_key)
    action = "created"
    if status_get == 200:
        status_del, del_body = request_fn("DELETE", f"{CREDENTIALS_ENDPOINT}/{cid}", resolved_key)
        if status_del not in (200, 204):
            raise RuntimeError(f"Failed deleting existing credential '{cid}' (HTTP {status_del}): {del_body}")
        action = "recreated"
    elif status_get != 404:
        raise RuntimeError(f"Unexpected HTTP {status_get} checking credential '{cid}'.")

    status_post, post_body = request_fn("POST", CREDENTIALS_ENDPOINT, resolved_key, body=payload)
    if status_post not in (200, 201):
        raise RuntimeError(f"Failed creating credential '{cid}' (HTTP {status_post}): {post_body}")

    return {
        "credential_id": cid,
        "trusted_domains": list(trusted_domains),
        "action": action,
        "status": "ok",
    }


def deploy_agents(
    agent_names: Optional[List[str]] = None,
    agents_dir: Optional[Path] = None,
    prefix: Optional[str] = None,
    model_override: Optional[str] = None,
    dry_run: bool = False,
    recreate: bool = True,
    out_dir: Optional[Path] = None,
    api_key: Optional[str] = None,
    request_fn=_api_request,
) -> Dict[str, Any]:
    """Compile and deploy one or all agent packages under `agents/`."""
    root = agents_dir or default_agents_dir()
    resolved_prefix = os.environ.get("SIMON_AGENT_PREFIX", "") if prefix is None else prefix
    resolved_model = model_override or os.environ.get("SIMON_AGENT_MODEL_OVERRIDE") or None

    if agent_names:
        dirs = [root / name for name in agent_names]
        for d in dirs:
            if not d.is_dir():
                raise FileNotFoundError(f"Agent package directory not found: {d}")
    else:
        dirs = list_agent_packages(root)

    results: List[Dict[str, Any]] = []
    for agent_dir in dirs:
        compiled = compile_agent_package(
            agent_dir,
            prefix=resolved_prefix,
            model_override=resolved_model,
        )
        results.append(
            deploy_compiled_agent(
                compiled,
                api_key=api_key,
                dry_run=dry_run,
                recreate=recreate,
                out_dir=out_dir,
                request_fn=request_fn,
            )
        )

    return {
        "dry_run": dry_run,
        "prefix": resolved_prefix,
        "count": len(results),
        "agents": results,
    }
