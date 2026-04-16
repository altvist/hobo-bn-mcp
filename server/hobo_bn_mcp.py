"""
-----------------------------------------------------
HOBO BN MCP v1.1.0
Minimal REST no-dependencies server for Binary Ninja
-----------------------------------------------------

Author: ALTVIST (contact@altvi.st)

Thanks Anthropic (https://www.anthropic.com/) for
Claude (https://claude.ai), it helps a lot!

The server starts automatically when Binary Ninja loads this plugin.
Each opened binary gets an auto-incremented ID. All commands (except
meta) require an explicit "bv" parameter to identify the target.

From a client:
    curl -s http://localhost:13337/cmd/ping
    curl -s http://localhost:13337/cmd/list_views
    curl -s -X POST http://localhost:13337/cmd/decompile \\
      -H "Content-Type: application/json" \\
      -d '{"bv":"0","name":"main"}'
"""

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from __future__ import annotations

import base64
import json
import threading
from collections import deque
from datetime import datetime, timezone
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

# The version (do not forget to change it every release!)
HOBO_MCP_VERSION = "v1.1.0"

# Debug messages
LOG_DEBUG_MSG = False


# ---------------------------------------------------------------------------
# Logger (prints to Binary Ninja console)
# ---------------------------------------------------------------------------

class Log:

    TAG = "hobo_bn_mcp"

    @staticmethod
    def msg(msg, msg_type):
        ts = datetime.now(timezone.utc).replace(microsecond=0)
        print(f"[{ts}] [{Log.TAG}] [{msg_type}] {msg}")

    @staticmethod
    def info(msg):
        Log.msg(msg, "INFO")

    @staticmethod
    def warning(msg):
        Log.msg(msg, "WARNING!")

    @staticmethod
    def error(msg):
        Log.msg(msg, "ERROR!")

    @staticmethod
    def debug(msg):
        if LOG_DEBUG_MSG:
            Log.msg(msg, "DEBUG")


# ---------------------------------------------------------------------------
# Try to import binaryninja
# ---------------------------------------------------------------------------

try:
    import binaryninja  # type: ignore
    from binaryninja.enums import SymbolType
except ImportError:
    binaryninja = None
    SymbolType = None
    Log.error("Can't import binaryninja, commands will fail outside BN")

# Default IP/port
DEFAULT_IP = "127.0.0.1"
DEFAULT_PORT = 13337


# ---------------------------------------------------------------------------
# BinaryView registry
# ---------------------------------------------------------------------------

_views: Dict[str, dict] = {}   # id -> {"bv": <BinaryView>, "filename": ..., ...}
_next_id: int = 0
_views_lock = threading.Lock()


def _register_bv(bv) -> str:
    """Register a BinaryView and return its ID."""
    global _next_id
    with _views_lock:
        # Check if this exact bv object is already registered
        for vid, entry in _views.items():
            if entry["bv"] is bv:
                Log.debug(f"BinaryView already registered as id={vid}")
                return vid

        # Prune stale entries for the same file
        filename = bv.file.filename
        stale = []
        for vid, entry in _views.items():
            try:
                _ = entry["bv"].start
            except Exception:
                stale.append(vid)
                continue
            # Same file + same view type — old BV replaced by new analysis
            if entry["filename"] == filename and \
               entry["bv"].view_type == bv.view_type:
                stale.append(vid)

        for vid in stale:
            Log.info(f"Pruning stale BinaryView id={vid}: {_views[vid]['filename']}")
            del _views[vid]

        vid = str(_next_id)
        _next_id += 1
        _views[vid] = {
            "bv": bv,
            "filename": filename,
            "arch": bv.arch.name if bv.arch else "unknown",
            "platform": bv.platform.name if bv.platform else "unknown",
        }
        Log.info(f"Registered BinaryView id={vid}: {filename}")
        return vid


def _get_bv_entry(vid: str) -> dict:
    """Get a registry entry by ID. Raises ValueError if not found."""
    with _views_lock:
        entry = _views.get(vid)
    if entry is None:
        raise ValueError(
            f"Unknown BinaryView id={vid}. "
            f"Use 'list_views' to see available views."
        )
    return entry


def _validate_bv(entry: dict) -> Any:
    """Check that the BinaryView is still usable. Returns the bv object."""
    bv = entry["bv"]
    try:
        _ = bv.start
        return bv
    except Exception:
        raise RuntimeError(
            f"BinaryView id for '{entry['filename']}' is no longer valid. "
            f"The file may have been closed. Please reopen it in Binary Ninja "
            f"and check 'list_views' for the new ID."
        )


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

_commands: Dict[str, Callable] = {}


def command(name: Optional[str] = None):
    """Register a command handler.

    The handler receives parsed JSON body (dict) for POST, or {} for GET.
    Must return a JSON-serialisable value.
    """
    def decorator(fn: Callable):
        cmd_name = name or fn.__name__
        _commands[cmd_name] = fn
        @wraps(fn)
        def wrapper(*a, **kw):
            return fn(*a, **kw)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_bv(params: dict):
    """Resolve and validate BinaryView from params["bv"]. Returns (bv, vid)."""
    vid = params.get("bv")
    if vid is None:
        raise ValueError(
            "Missing required parameter 'bv'. "
            "Use 'list_views' to see available BinaryView IDs."
        )
    vid = str(vid)
    entry = _get_bv_entry(vid)
    bv = _validate_bv(entry)
    return bv, vid


def _parse_addr(val) -> int:
    """Accept '0x1234', '1234' (decimal), or int."""
    if isinstance(val, str):
        return int(val, 16) if val.startswith("0x") else int(val)
    return int(val)


def _resolve_function(bv, params: dict):
    """Resolve a function by 'address' or 'name' param."""
    if "address" in params:
        addr = _parse_addr(params["address"])
        func = bv.get_function_at(addr)
        if func is None:
            containing = bv.get_functions_containing(addr)
            if containing:
                func = containing[0]
        if func is None:
            raise ValueError(f"No function at {hex(addr)}")
        return func

    if "name" in params:
        target = params["name"]
        # Try BN's built-in lookup first (exact match)
        funcs = bv.get_functions_by_name(target)
        if not funcs:
            # Fallback: substring search across all name forms
            target_lower = target.lower()
            for fn in bv.functions:
                sym = fn.symbol
                if sym is None:
                    continue
                if target_lower in sym.full_name.lower() or \
                   target_lower in sym.short_name.lower() or \
                   target_lower in sym.raw_name.lower():
                    funcs = [fn]
                    break
        if not funcs:
            raise ValueError(f"No function named '{params['name']}'")
        return funcs[0]

    raise ValueError("Provide 'address' or 'name'")


def _get_comment(bv, addr, func=None):
    """Get combined BV-level + function-level comment at addr."""
    parts = []
    bv_comment = bv.get_comment_at(addr)
    if bv_comment:
        parts.append(bv_comment)
    if func is not None:
        func_comment = func.get_comment_at(addr)
        if func_comment:
            parts.append(func_comment)
    return "\n".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Commands — meta
# ---------------------------------------------------------------------------

@command("ping")
def _cmd_ping(params: dict) -> Any:
    """Ping (is the server still alive)"""
    return {"status": "pong"}


@command("version")
def _cmd_version(params: dict) -> Any:
    """Get server and Binary Ninja version"""
    ver = "unknown"
    if binaryninja is not None:
        try:
            ver = binaryninja.core_version()
        except Exception:
            pass
    return {"binary_ninja_version": ver, "hobo_mcp_version": HOBO_MCP_VERSION}


@command("list_views")
def _cmd_list_views(params: dict) -> Any:
    """List all currently registered BinaryViews with their status."""
    result = []
    with _views_lock:
        for vid, entry in _views.items():
            bv = entry["bv"]
            status = "unknown"
            try:
                _ = bv.start
                status = "ready"
            except Exception:
                status = "closed"

            result.append({
                "id": vid,
                "filename": entry["filename"],
                "path": entry.get("filename", ""),
                "arch": entry["arch"],
                "platform": entry["platform"],
                "status": status,
            })
    return {"views": result}


# ---------------------------------------------------------------------------
# Commands — orientation
# ---------------------------------------------------------------------------

@command("binary_info")
def _cmd_binary_info(params: dict) -> Any:
    """Get binary info"""
    bv, vid = _require_bv(params)
    return {
        "bv": vid,
        "filename": bv.file.filename,
        "arch": bv.arch.name,
        "platform": bv.platform.name,
        "base_address": hex(bv.start),
        "entry_point": hex(bv.entry_point),
        "endianness": str(bv.endianness),
        "address_size": bv.address_size,
        "num_functions": len(bv.functions),
        "num_segments": len(bv.segments),
        "num_sections": len(bv.sections),
    }


@command("sections")
def _cmd_sections(params: dict) -> Any:
    """List sections"""
    bv, vid = _require_bv(params)
    result = []
    for name, sec in bv.sections.items():
        result.append({
            "name": name,
            "start": hex(sec.start),
            "end": hex(sec.end),
            "length": sec.length,
            "semantics": str(sec.semantics),
        })
    return {"bv": vid, "sections": result}


@command("imports")
def _cmd_imports(params: dict) -> Any:
    """List imported functions.  Optional 'filter' substring."""
    bv, vid = _require_bv(params)
    filt = params.get("filter", "").lower()
    result = []
    for sym in bv.get_symbols_of_type(SymbolType.ImportedFunctionSymbol):
        name = sym.full_name
        if filt and filt not in name.lower():
            continue
        result.append({"name": name, "address": hex(sym.address)})
    return {"bv": vid, "imports": result}


@command("exports")
def _cmd_exports(params: dict) -> Any:
    """List exported symbols.  Optional 'filter' substring."""
    bv, vid = _require_bv(params)
    filt = params.get("filter", "").lower()
    result = []
    for stype in (SymbolType.FunctionSymbol, SymbolType.DataSymbol):
        for sym in bv.get_symbols_of_type(stype):
            if sym.name.startswith("sub_"):
                continue
            name = sym.full_name
            if filt and filt not in name.lower():
                continue
            result.append({
                "name": name,
                "address": hex(sym.address),
                "type": str(stype).split(".")[-1],
            })
    return {"bv": vid, "exports": result}


# ---------------------------------------------------------------------------
# Commands — function navigation
# ---------------------------------------------------------------------------

@command("functions")
def _cmd_functions(params: dict) -> Any:
    """List functions.  Optional 'filter', 'limit' (default 100), 'offset'."""
    bv, vid = _require_bv(params)
    filt = params.get("filter", "").lower()
    limit = min(int(params.get("limit", 100)), 5000)
    offset = int(params.get("offset", 0))

    matched = []
    for fn in bv.functions:
        # Collect all name forms for matching
        sym = fn.symbol
        display_name = sym.full_name if sym else fn.name
        if filt:
            names = {fn.name}
            if sym is not None:
                names.update((sym.full_name, sym.short_name, sym.raw_name))
            names_lower = " ".join(names).lower()
            if filt not in names_lower:
                continue

        entry = {
            "name": display_name,
            "address": hex(fn.start),
            "size": fn.total_bytes,
        }
        comment = _get_comment(bv, fn.start, fn)
        if comment:
            entry["comment"] = comment
        matched.append(entry)

    total = len(matched)
    return {
        "bv": vid,
        "total": total,
        "offset": offset,
        "limit": limit,
        "functions": matched[offset : offset + limit],
    }

@command("decompile")
def _cmd_decompile(params: dict) -> Any:
    """Decompile (HLIL) a function.  Identify by 'address' or 'name'."""
    bv, vid = _require_bv(params)
    func = _resolve_function(bv, params)
    try:
        hlil = func.hlil
    except Exception as exc:
        raise RuntimeError(f"HLIL unavailable for {func.name}: {exc}")

    lines = []
    for instr in hlil.instructions:
        line = str(instr)
        comment = _get_comment(bv, instr.address, func)
        if comment:
            flat = comment.replace("\n", " | ")
            line += f"  // {flat}"
        lines.append(line)

    header_comment = _get_comment(bv, func.start, func)
    result = {
        "bv": vid,
        "name": func.name,
        "address": hex(func.start),
        "code": "\n".join(lines),
    }
    if header_comment:
        result["comment"] = header_comment
    return result


@command("disasm")
def _cmd_disasm(params: dict) -> Any:
    """Disassemble a function.  Identify by 'address' or 'name'."""
    bv, vid = _require_bv(params)
    func = _resolve_function(bv, params)

    instructions = []
    for block in sorted(func.basic_blocks, key=lambda b: b.start):
        for line in block.disassembly_text:
            text = "".join(str(t) for t in line.tokens)
            entry = {
                "address": hex(line.address),
                "text": text,
            }
            comment = _get_comment(bv, line.address, func)
            if comment:
                entry["comment"] = comment
            instructions.append(entry)

    result = {
        "bv": vid,
        "name": func.name,
        "address": hex(func.start),
        "instructions": instructions,
    }
    header_comment = _get_comment(bv, func.start, func)
    if header_comment:
        result["comment"] = header_comment
    return result


# ---------------------------------------------------------------------------
# Commands — cross-references & call graph
# ---------------------------------------------------------------------------

@command("xrefs_to")
def _cmd_xrefs_to(params: dict) -> Any:
    """Code & data references TO an address."""
    bv, vid = _require_bv(params)
    addr = _parse_addr(params["address"])

    code_refs = []
    for ref in bv.get_code_refs(addr):
        caller = ref.function
        code_refs.append({
            "from": hex(ref.address),
            "function": caller.name if caller else None,
        })

    data_refs = [{"from": hex(r)} for r in bv.get_data_refs(addr)]

    return {
        "bv": vid,
        "address": hex(addr),
        "code_refs": code_refs,
        "data_refs": data_refs,
    }


@command("xrefs_from")
def _cmd_xrefs_from(params: dict) -> Any:
    """What does this function call / reference?"""
    bv, vid = _require_bv(params)
    func = _resolve_function(bv, params)

    callees = {}
    for block in func.basic_blocks:
        for line in block.disassembly_text:
            for target in bv.get_code_refs_from(line.address):
                target_func = bv.get_function_at(target)
                if target_func and target_func.start not in callees:
                    callees[target_func.start] = target_func.name

    result_list = [{"address": hex(a), "name": n} for a, n in callees.items()]
    return {
        "bv": vid,
        "function": func.name,
        "address": hex(func.start),
        "callees": result_list,
    }


@command("callers")
def _cmd_callers(params: dict) -> Any:
    """Transitive callers (BFS) up to 'depth' levels (default 3, max 10)."""
    bv, vid = _require_bv(params)
    func = _resolve_function(bv, params)
    max_depth = min(int(params.get("depth", 3)), 10)

    visited = set()
    edges = []
    queue = deque([(func, 0)])

    while queue:
        fn, depth = queue.popleft()
        if fn.start in visited or depth >= max_depth:
            continue
        visited.add(fn.start)

        for ref in bv.get_code_refs(fn.start):
            caller = ref.function
            if caller and caller.start not in visited:
                edges.append({
                    "caller": caller.name,
                    "caller_addr": hex(caller.start),
                    "callee": fn.name,
                    "callee_addr": hex(fn.start),
                    "site": hex(ref.address),
                    "depth": depth + 1,
                })
                queue.append((caller, depth + 1))

    return {
        "bv": vid,
        "target": func.name,
        "max_depth": max_depth,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Commands — data & types
# ---------------------------------------------------------------------------

@command("strings")
def _cmd_strings(params: dict) -> Any:
    """Strings from the binary.  Optional 'filter', 'limit', 'offset', 'min_length'."""
    bv, vid = _require_bv(params)
    filt = params.get("filter", "").lower()
    limit = min(int(params.get("limit", 200)), 5000)
    offset = int(params.get("offset", 0))
    min_len = int(params.get("min_length", 4))

    matched = []
    for s in bv.strings:
        val = s.value
        if len(val) < min_len:
            continue
        if filt and filt not in val.lower():
            continue
        matched.append({
            "address": hex(s.start),
            "length": s.length,
            "value": val,
        })

    total = len(matched)
    return {
        "bv": vid,
        "total": total,
        "offset": offset,
        "limit": limit,
        "strings": matched[offset : offset + limit],
    }


@command("variables")
def _cmd_variables(params: dict) -> Any:
    """Parameters and local variables of a function."""
    bv, vid = _require_bv(params)
    func = _resolve_function(bv, params)

    param_vars = []
    for v in func.parameter_vars:
        param_vars.append({"name": v.name, "type": str(v.type)})

    param_names = {v.name for v in func.parameter_vars}
    local_vars = []
    for v in func.vars:
        if v.name in param_names:
            continue
        local_vars.append({
            "name": v.name,
            "type": str(v.type),
            "source": str(v.source_type),
        })

    return {
        "bv": vid,
        "function": func.name,
        "address": hex(func.start),
        "parameters": param_vars,
        "locals": local_vars,
    }


@command("types")
def _cmd_types(params: dict) -> Any:
    """Named types (structs, enums, typedefs).  Optional 'filter', 'limit', 'offset'."""
    bv, vid = _require_bv(params)
    filt = params.get("filter", "").lower()
    limit = min(int(params.get("limit", 50)), 500)
    offset = int(params.get("offset", 0))

    matched = []
    for qname, ty in bv.types.items():
        name = str(qname)
        if filt and filt not in name.lower():
            continue
        matched.append({
            "name": name,
            "definition": str(ty),
            "width": ty.width,
        })

    total = len(matched)
    return {
        "bv": vid,
        "total": total,
        "offset": offset,
        "limit": limit,
        "types": matched[offset : offset + limit],
    }


# ---------------------------------------------------------------------------
# Commands — raw data
# ---------------------------------------------------------------------------

@command("read_bytes")
def _cmd_read_bytes(params: dict) -> Any:
    """Read raw bytes.  'address' (required), 'length' (default 256, max 4096)."""
    bv, vid = _require_bv(params)
    addr = _parse_addr(params["address"])
    length = min(int(params.get("length", 256)), 4096)

    data = bv.read(addr, length)
    if len(data) < 1:
        raise ValueError(f"Can't read data from the address {hex(addr)}!")

    result = {
        "bv": vid,
        "address": hex(addr),
        "length": len(data),
        "hex": data.hex(),
        "base64": base64.b64encode(data).decode(),
    }
    comment = _get_comment(bv, addr)
    if comment:
        result["comment"] = comment
    return result


# ---------------------------------------------------------------------------
# Commands — comments
# ---------------------------------------------------------------------------

@command("get_comment")
def _cmd_get_comment(params: dict) -> Any:
    """Get comment at an address."""
    bv, vid = _require_bv(params)
    addr = _parse_addr(params["address"])

    result = {"bv": vid, "address": hex(addr)}

    bv_comment = bv.get_comment_at(addr)
    if bv_comment:
        result["bv_comment"] = bv_comment

    funcs = bv.get_functions_containing(addr)
    if funcs:
        func = funcs[0]
        result["function"] = func.name
        func_comment = func.get_comment_at(addr)
        if func_comment:
            result["func_comment"] = func_comment

    return result


@command("set_comment")
def _cmd_set_comment(params: dict) -> Any:
    """Set a comment at an address."""
    bv, vid = _require_bv(params)
    addr = _parse_addr(params["address"])
    text = params.get("comment", "")
    level = params.get("level", "function")
    append = params.get("append", False)

    if level == "function":
        funcs = bv.get_functions_containing(addr)
        if not funcs:
            raise ValueError(
                f"No function contains {hex(addr)} — use level='bv' "
                f"for addresses outside functions"
            )
        func = funcs[0]

        if append:
            existing = func.get_comment_at(addr) or ""
            text = (existing + "\n" + text).strip() if existing else text

        func.set_comment_at(addr, text)
        return {
            "bv": vid,
            "address": hex(addr),
            "function": func.name,
            "level": "function",
            "comment": text,
        }
    else:
        if append:
            existing = bv.get_comment_at(addr) or ""
            text = (existing + "\n" + text).strip() if existing else text

        bv.set_comment_at(addr, text)
        return {
            "bv": vid,
            "address": hex(addr),
            "level": "bv",
            "comment": text,
        }

# ---------------------------------------------------------------------------
# Commands - debug (not documented in the user guide)
# ---------------------------------------------------------------------------

@command("debug_bv_state")
def _cmd_debug_bv_state(params: dict) -> Any:
    """Dump BV internals to find a reliable 'closed' indicator."""
    results = []
    with _views_lock:
        for vid, entry in _views.items():
            bv = entry["bv"]
            state = {"id": vid, "filename": entry["filename"]}
            checks = {}

            try: checks["file_is_none"] = bv.file is None
            except Exception as e: checks["file_is_none"] = f"ERR: {e}"

            try: checks["filename"] = bv.file.filename
            except Exception as e: checks["filename"] = f"ERR: {e}"

            try: checks["view_type"] = bv.view_type
            except Exception as e: checks["view_type"] = f"ERR: {e}"

            try: checks["start"] = hex(bv.start)
            except Exception as e: checks["start"] = f"ERR: {e}"

            try: checks["segments"] = len(bv.segments)
            except Exception as e: checks["segments"] = f"ERR: {e}"

            try: checks["functions"] = len(bv.functions)
            except Exception as e: checks["functions"] = f"ERR: {e}"

            try: checks["read_1_byte"] = bv.read(bv.start, 1).hex()
            except Exception as e: checks["read_1_byte"] = f"ERR: {e}"

            try: checks["session_id"] = bv.file.session_id
            except Exception as e: checks["session_id"] = f"ERR: {e}"

            try: checks["has_database"] = bv.file.has_database
            except Exception as e: checks["has_database"] = f"ERR: {e}"

            try: checks["raw_length"] = bv.file.raw.length
            except Exception as e: checks["raw_length"] = f"ERR: {e}"

            try: checks["raw_is_none"] = bv.file.raw is None
            except Exception as e: checks["raw_is_none"] = f"ERR: {e}"

            try: checks["analysis_progress"] = str(bv.analysis_progress)
            except Exception as e: checks["analysis_progress"] = f"ERR: {e}"

            state["checks"] = checks
            results.append(state)

    return {"views": results}

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """Routes: GET/POST  /cmd/<command_name>"""

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def log_message(self, fmt, *args):
        Log.debug(fmt % args)

    def _dispatch(self):
        path = self.path.rstrip("/")

        if path == "/cmd":
            self._json_ok({"commands": sorted(_commands.keys())})
            return

        if path.startswith("/cmd/"):
            cmd_name = path[len("/cmd/"):]
            handler = _commands.get(cmd_name)
            if handler is None:
                self._json_err(404, f"unknown command: {cmd_name}")
                return
            body = self._read_json_body()
            try:
                result = handler(body)
                self._json_ok(result)
            except Exception as exc:
                Log.error(f"command '{cmd_name}' failed: {exc}")
                self._json_err(500, str(exc))
            return

        self._json_err(404, "not found — try GET /cmd for command list")

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _json_ok(self, data: Any):
        self._send_json(200, {"ok": True, "data": data})

    def _json_err(self, code: int, msg: str):
        self._send_json(code, {"ok": False, "error": msg})

    def _send_json(self, code: int, obj: Any):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

_server: Optional[ThreadingHTTPServer] = None
_thread: Optional[threading.Thread] = None


def _ensure_server(host: str = DEFAULT_IP, port: int = DEFAULT_PORT) -> None:
    """Start the server if it's not already running."""
    global _server, _thread

    if _server is not None:
        return

    _server = ThreadingHTTPServer((host, port), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    Log.info(f"listening on http://{host}:{port}/")


def start(host: str = DEFAULT_IP, port: int = DEFAULT_PORT) -> None:
    """Manually start the server (if auto-start didn't run or you need a different port)."""
    if _server is not None:
        Log.warning("Server already running — call stop() first")
        return
    _ensure_server(host, port)


def stop() -> None:
    """Shut down the server."""
    global _server, _thread

    if _server is None:
        return

    _server.shutdown()
    _server.server_close()
    _server = None
    _thread = None
    Log.info("stopped")


# ---------------------------------------------------------------------------
# BinaryView event callback — auto-register new views
# ---------------------------------------------------------------------------

def _on_bv_analysis_complete(bv) -> None:
    """Called by BN when initial analysis of a BinaryView completes."""
    # Skip raw/mapped views that have no arch (e.g. "Raw", "Mapped")
    if (bv.arch is None) or (bv.view_type == "Raw"):
        return
    _register_bv(bv)
    _ensure_server()

# ---------------------------------------------------------------------------
# Plugin registration (auto-start)
# ---------------------------------------------------------------------------

if binaryninja is not None:
    binaryninja.BinaryViewEvent.register(
        binaryninja.BinaryViewEventType.BinaryViewInitialAnalysisCompletionEvent,
        _on_bv_analysis_complete,
    )
    Log.info(
        f"HOBO BN MCP {HOBO_MCP_VERSION} "
        f"plugin registered — server will start when a file is opened"
    )