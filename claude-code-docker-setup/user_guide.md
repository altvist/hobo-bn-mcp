# HOBO BN MCP v1.1.0 — User Guide

## Table of contents

- [What is HOBO BN MCP](#what-is-hobo-bn-mcp)
- [Installation](#installation)
- [Getting started](#getting-started)
- [Concepts](#concepts)
  - [BinaryView IDs](#binaryview-ids)
  - [Request format](#request-format)
  - [Response format](#response-format)
  - [Function identification](#function-identification)
  - [Function name matching](#function-name-matching)
  - [Pagination](#pagination)
  - [Comments](#comments-concept)
- [Command reference](#command-reference)
  - [Meta commands](#meta-commands) — `ping`, `version`, `commands`, `list_views`
  - [Binary information](#binary-information) — `binary_info`, `sections`, `imports`, `exports`
  - [Function navigation](#function-navigation) — `functions`, `decompile`, `disasm`
  - [Cross-references and call graph](#cross-references-and-call-graph) — `xrefs_to`, `xrefs_from`, `callers`
  - [Data and types](#data-and-types) — `strings`, `variables`, `types`
  - [Raw data](#raw-data) — `read_bytes`
  - [Comments](#comments) — `get_comment`, `set_comment`
- [Error handling](#error-handling)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

## What is HOBO BN MCP

HOBO BN MCP is a lightweight REST server that runs inside [Binary Ninja](https://binary.ninja/) as a plugin. It exposes Binary Ninja's analysis capabilities — decompilation, disassembly, cross-references, type information, and more — over HTTP, so you can interact with your reverse engineering project from the command line, scripts, LLM agents, or any HTTP client.

Despite its name, HOBO BN MCP is **not** an MCP (Model Context Protocol) server. It uses a simple JSON-over-HTTP protocol with zero external dependencies. The entire server is a single Python file that runs on Binary Ninja's built-in Python interpreter.

**Key features:**

- **Zero dependencies.** One `.py` file, no `pip install` required.
- **Auto-start.** The server starts automatically when you open a file in Binary Ninja.
- **Multi-binary.** Multiple files can be open simultaneously, each with its own ID.
- **Read + comment.** Full read access to Binary Ninja's analysis, plus the ability to set comments.
- **Any client.** Works with `curl`, Python scripts, browsers, Postman, LLM agents — anything that speaks HTTP.
- **Any license.** Works with Binary Ninja Personal ($299). No headless ($1499+) license required.

## Installation

1. Locate your Binary Ninja plugins directory:

   | OS      | Path                                                  |
   |---------|-------------------------------------------------------|
   | macOS   | `~/Library/Application Support/Binary Ninja/plugins/` |
   | Linux   | `~/.binaryninja/plugins/`                             |
   | Windows | `%APPDATA%\Binary Ninja\plugins\`                     |

2. Copy `hobo_bn_mcp.py` into that directory.

3. Restart Binary Ninja (or open a new file — the plugin loads on startup).

4. Verify from a terminal:

   ```bash
   curl -s http://localhost:13337/cmd/ping
   ```

   Expected response: `{"ok":true,"data":{"status":"pong"}}`

## Getting started

### Quick workflow example

```bash
# 1. Check server is alive
curl -s http://localhost:13337/cmd/ping

# 2. See which binaries are open
curl -s http://localhost:13337/cmd/list_views

# 3. Get basic info about binary with id "0"
curl -s -X POST http://localhost:13337/cmd/binary_info \
  -H "Content-Type: application/json" \
  -d '{"bv":"0"}'

# 4. List functions containing "parse" in their name
curl -s -X POST http://localhost:13337/cmd/functions \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","filter":"parse","limit":20}'

# 5. Decompile a function
curl -s -X POST http://localhost:13337/cmd/decompile \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"main"}'

# 6. Find who calls a function at a given address
curl -s -X POST http://localhost:13337/cmd/xrefs_to \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40"}'

# 7. Leave a comment
curl -s -X POST http://localhost:13337/cmd/set_comment \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40","comment":"TODO: check bounds"}'
```

## Concepts

### BinaryView IDs

Every binary opened in Binary Ninja gets a unique auto-incremented integer ID: `"0"`, `"1"`, `"2"`, etc. All commands (except meta commands) require an explicit `"bv"` parameter with this ID.

IDs are **never reused**. If you close a binary that had id `"2"` and open a new file, the new file gets id `"3"`. The old id `"2"` becomes permanently invalid.

Internal Binary Ninja views (such as "Raw" views with no architecture) are automatically filtered out and do not receive IDs.

Use `list_views` to see all currently available IDs.

### Request format

Commands are accessed via `GET` or `POST` to `/cmd/<command_name>`.

**GET** — for commands with no parameters:

```bash
curl -s http://localhost:13337/cmd/ping
```

**POST** — for commands with parameters (JSON body):

```bash
curl -s -X POST http://localhost:13337/cmd/decompile \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"main"}'
```

The `Content-Type: application/json` header is recommended but not strictly required — the server will attempt to parse JSON from the body regardless.

### Response format

Every response is a JSON object with one of two shapes:

**Success:**

```json
{
  "ok": true,
  "data": { ... }
}
```

**Error:**

```json
{
  "ok": false,
  "error": "description of what went wrong"
}
```

HTTP status codes: `200` for success, `404` for unknown commands, `500` for command execution errors.

Most successful responses include a `"bv"` field in `"data"` confirming which BinaryView was used. This lets you verify that you're working with the correct binary.

### Function identification

Many commands accept a function as a parameter. Functions can be identified in two ways:

- **By address:** `"address": "0x100003a40"` — hex string (with `0x` prefix) or decimal integer.
- **By name:** `"name": "main"` — function name as a string.

These are mutually exclusive — provide one or the other, not both.

When using an address, the server first tries to find a function starting at that exact address. If not found, it falls back to finding a function that *contains* that address. This means you can pass any address inside a function's body, not just its entry point.

### Function name matching

Function name matching works in two stages:

1. **Exact match** via Binary Ninja's built-in `get_functions_by_name()`.
2. **Substring fallback** — if the exact match fails, the server searches through all functions, checking each function's symbol `full_name`, `short_name`, and `raw_name`. This means you can search by:
   - Short name: `"IsDataFormatSupported"`
   - Full demangled name with class: `"NextAudioFile::IsDataFormatSupported"`
   - Mangled name: `"_ZN13NextAudioFile22IsDataFormatSupportedEv"`

The same multi-form matching applies to the `filter` parameter in the `functions` command.

The `functions` command also displays functions using their `full_name` (the fully qualified demangled name, e.g. `NextAudioFile::IsDataFormatSupported`) rather than the short name, so you always see the full context including class/namespace.

### Pagination

Commands that can return large result sets (`functions`, `strings`, `types`) support pagination:

- `limit` — maximum number of results to return (each command has its own default and maximum).
- `offset` — number of results to skip from the beginning.

Example — get functions 100-199:

```bash
curl -s -X POST http://localhost:13337/cmd/functions \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","limit":100,"offset":100}'
```

The response includes `total` (total number of matching results before pagination), `offset`, and `limit` fields so you know how many pages exist.

### Comments concept

Binary Ninja supports two levels of comments:

- **Function-level comments** — attached to a specific address within a function. Visible in the decompilation and disassembly views. These are the most common type.
- **BinaryView-level (BV) comments** — attached to an address globally, not tied to any specific function. Useful for commenting on data addresses or addresses outside of functions.

The `set_comment` command defaults to function-level. Use `"level":"bv"` for BV-level comments.

When reading comments (via `decompile`, `disasm`, `get_comment`, etc.), both levels are checked and returned.

## Command reference

### Meta commands

These commands do not require a `"bv"` parameter.

#### `ping`

Check that the server is alive and responding.

```bash
curl -s http://localhost:13337/cmd/ping
```

**Response:**

```json
{"ok":true,"data":{"status":"pong"}}
```

#### `version`

Get server and Binary Ninja version information.

```bash
curl -s http://localhost:13337/cmd/version
```

**Response:**

```json
{
  "ok": true,
  "data": {
    "binary_ninja_version": "4.2.6789",
    "hobo_mcp_version": [2, 0, 0]
  }
}
```

#### `commands`

List all registered commands on the server.

```bash
curl -s http://localhost:13337/cmd
```

**Response:**

```json
{
  "ok": true,
  "data": {
    "commands": ["binary_info", "callers", "decompile", "disasm", "exports",
                 "functions", "get_comment", "imports", "list_views", "ping",
                 "read_bytes", "sections", "set_comment", "strings", "types",
                 "variables", "version", "xrefs_from", "xrefs_to"]
  }
}
```

#### `list_views`

List all registered BinaryViews and their status.

```bash
curl -s http://localhost:13337/cmd/list_views
```

**Response:**

```json
{
  "ok": true,
  "data": {
    "views": [
      {
        "id": "0",
        "filename": "/Users/user/re/vuln_app",
        "path": "/Users/user/re/vuln_app",
        "arch": "aarch64",
        "platform": "mac-aarch64",
        "status": "ready"
      },
      {
        "id": "1",
        "filename": "/Users/user/re/libparser.dylib",
        "path": "/Users/user/re/libparser.dylib",
        "arch": "aarch64",
        "platform": "mac-aarch64",
        "status": "ready"
      }
    ]
  }
}
```

**Status values:**

| Status  | Meaning                                                 |
|---------|---------------------------------------------------------|
| `ready` | The BinaryView is open and usable                       |
| `closed`| The file was closed in BN; this ID is no longer valid   |

**Tip:** always call `list_views` at the start of a session to discover available IDs, and again whenever you suspect the user has opened or closed files.

### Binary information

All commands in this section require `"bv"`.

#### `binary_info`

Get metadata about the binary.

```bash
curl -s -X POST http://localhost:13337/cmd/binary_info \
  -H "Content-Type: application/json" \
  -d '{"bv":"0"}'
```

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "filename": "/Users/user/re/vuln_app",
    "arch": "aarch64",
    "platform": "mac-aarch64",
    "base_address": "0x100000000",
    "entry_point": "0x100003a40",
    "endianness": "LittleEndian",
    "address_size": 8,
    "num_functions": 342,
    "num_segments": 5,
    "num_sections": 12
  }
}
```

**Fields:**

| Field           | Description                                            |
|-----------------|--------------------------------------------------------|
| `filename`      | Full path to the binary file                           |
| `arch`          | CPU architecture (`aarch64`, `x86_64`, `armv7`, etc.)  |
| `platform`      | Platform (`mac-aarch64`, `linux-x86_64`, etc.)         |
| `base_address`  | Base load address                                      |
| `entry_point`   | Entry point address                                    |
| `endianness`    | `LittleEndian` or `BigEndian`                          |
| `address_size`  | Address size in bytes (4 or 8)                         |
| `num_functions` | Total number of functions identified by BN             |
| `num_segments`  | Number of segments                                     |
| `num_sections`  | Number of sections                                     |

#### `sections`

List all sections in the binary.

```bash
curl -s -X POST http://localhost:13337/cmd/sections \
  -H "Content-Type: application/json" \
  -d '{"bv":"0"}'
```

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "sections": [
      {
        "name": "__TEXT,__text",
        "start": "0x100003a40",
        "end": "0x100006f80",
        "length": 13632,
        "semantics": "ReadOnlyCodeSectionSemantics"
      },
      {
        "name": "__DATA,__data",
        "start": "0x100008000",
        "end": "0x100008120",
        "length": 288,
        "semantics": "ReadWriteDataSectionSemantics"
      }
    ]
  }
}
```

**Semantics values:**

| Value                              | Meaning                      |
|------------------------------------|------------------------------|
| `ReadOnlyCodeSectionSemantics`     | Executable code              |
| `ReadOnlyDataSectionSemantics`     | Read-only data (constants)   |
| `ReadWriteDataSectionSemantics`    | Writable data (globals, BSS) |
| `ExternalSectionSemantics`         | External/imported symbols    |
| `DefaultSectionSemantics`          | Unclassified                 |

#### `imports`

List imported functions (symbols from external libraries).

```bash
# All imports
curl -s -X POST http://localhost:13337/cmd/imports \
  -H "Content-Type: application/json" \
  -d '{"bv":"0"}'

# Filtered by substring
curl -s -X POST http://localhost:13337/cmd/imports \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","filter":"memcpy"}'
```

**Parameters:**

| Parameter | Type   | Required | Default | Description            |
|-----------|--------|----------|---------|------------------------|
| `bv`      | string | yes      | —       | BinaryView ID          |
| `filter`  | string | no       | `""`    | Case-insensitive substring filter |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "imports": [
      {"name": "_memcpy", "address": "0x100007f00"},
      {"name": "_memmove", "address": "0x100007f20"}
    ]
  }
}
```

#### `exports`

List exported symbols (public API of the binary).

```bash
curl -s -X POST http://localhost:13337/cmd/exports \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","filter":"init"}'
```

**Parameters:**

| Parameter | Type   | Required | Default | Description            |
|-----------|--------|----------|---------|------------------------|
| `bv`      | string | yes      | —       | BinaryView ID          |
| `filter`  | string | no       | `""`    | Case-insensitive substring filter |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "exports": [
      {"name": "_main", "address": "0x100003a40", "type": "FunctionSymbol"},
      {"name": "_config_data", "address": "0x100008000", "type": "DataSymbol"}
    ]
  }
}
```

Auto-generated names (`sub_*`) are automatically excluded.

### Function navigation

#### `functions`

List functions with optional filtering and pagination.

```bash
# First 20 functions
curl -s -X POST http://localhost:13337/cmd/functions \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","limit":20}'

# Search by name (matches full_name, short_name, and raw_name)
curl -s -X POST http://localhost:13337/cmd/functions \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","filter":"AudioFile","limit":50}'

# Paginate
curl -s -X POST http://localhost:13337/cmd/functions \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","limit":100,"offset":200}'
```

**Parameters:**

| Parameter | Type   | Required | Default | Max  | Description                    |
|-----------|--------|----------|---------|------|--------------------------------|
| `bv`      | string | yes      | —       | —    | BinaryView ID                  |
| `filter`  | string | no       | `""`    | —    | Substring match (see [Function name matching](#function-name-matching)) |
| `limit`   | int    | no       | 100     | 5000 | Max results to return          |
| `offset`  | int    | no       | 0       | —    | Results to skip                |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "total": 342,
    "offset": 0,
    "limit": 20,
    "functions": [
      {"name": "main", "address": "0x100003a40", "size": 256},
      {"name": "NextAudioFile::IsDataFormatSupported", "address": "0x100004100", "size": 128, "comment": "TODO: check this"}
    ]
  }
}
```

The `name` field shows the fully qualified demangled name (including class/namespace). The `comment` field is only present if a comment exists at the function's entry point.

#### `decompile`

Decompile a function to HLIL (High Level Intermediate Language) pseudo-code.

```bash
# By name
curl -s -X POST http://localhost:13337/cmd/decompile \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"main"}'

# By address
curl -s -X POST http://localhost:13337/cmd/decompile \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40"}'
```

**Parameters:**

| Parameter  | Type   | Required           | Description            |
|------------|--------|--------------------|------------------------|
| `bv`       | string | yes                | BinaryView ID          |
| `address`  | string | one of addr/name   | Function address       |
| `name`     | string | one of addr/name   | Function name          |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "name": "main",
    "address": "0x100003a40",
    "code": "int32_t arg1 = ...\nif (arg1 < 2) ...  // [claude] check bounds\nvoid* buf = malloc(0x100)",
    "comment": "entry point"
  }
}
```

The `code` field contains HLIL as plain text. Comments at instruction addresses are embedded inline as `// comment text` at the end of the corresponding line. The top-level `comment` field (if present) is the comment at the function's entry point.

**Possible error:** `"HLIL unavailable for <name>"` — Binary Ninja could not build the HLIL for this function (common with very small, obfuscated, or data-only functions). Use `disasm` as a fallback.

#### `disasm`

Get the disassembly (assembly instructions) of a function.

```bash
curl -s -X POST http://localhost:13337/cmd/disasm \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"main"}'
```

**Parameters:** same as `decompile`.

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "name": "main",
    "address": "0x100003a40",
    "instructions": [
      {"address": "0x100003a40", "text": "stp    x29, x30, [sp, #-0x10]!"},
      {"address": "0x100003a44", "text": "mov    x29, sp"},
      {"address": "0x100003a48", "text": "bl     _parse_input", "comment": "calls parser"}
    ],
    "comment": "entry point"
  }
}
```

Instructions are sorted by address within basic blocks. The `comment` field on individual instructions is only present where a comment exists.

### Cross-references and call graph

#### `xrefs_to`

Find all code and data references **to** a specific address.

```bash
curl -s -X POST http://localhost:13337/cmd/xrefs_to \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40"}'
```

**Parameters:**

| Parameter | Type   | Required | Description            |
|-----------|--------|----------|------------------------|
| `bv`      | string | yes      | BinaryView ID          |
| `address` | string | yes      | Target address         |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "address": "0x100003a40",
    "code_refs": [
      {"from": "0x100005678", "function": "_start"},
      {"from": "0x100005800", "function": "_init_subsystem"}
    ],
    "data_refs": [
      {"from": "0x100008010"}
    ]
  }
}
```

- `code_refs` — instructions that reference this address (calls, jumps, etc.). Includes the containing function name.
- `data_refs` — data pointers to this address (vtables, function pointer tables, etc.).

#### `xrefs_from`

Find all functions/addresses that a given function calls or references.

```bash
curl -s -X POST http://localhost:13337/cmd/xrefs_from \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"main"}'
```

**Parameters:**

| Parameter  | Type   | Required           | Description            |
|------------|--------|--------------------|------------------------|
| `bv`       | string | yes                | BinaryView ID          |
| `address`  | string | one of addr/name   | Function address       |
| `name`     | string | one of addr/name   | Function name          |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "function": "main",
    "address": "0x100003a40",
    "callees": [
      {"address": "0x100004100", "name": "_parse_input"},
      {"address": "0x100004500", "name": "_process_data"},
      {"address": "0x100007f00", "name": "_memcpy"}
    ]
  }
}
```

Results are deduplicated by callee address.

#### `callers`

Trace transitive callers of a function using BFS (breadth-first search), building a call graph upward.

```bash
curl -s -X POST http://localhost:13337/cmd/callers \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"_memcpy","depth":5}'
```

**Parameters:**

| Parameter  | Type   | Required           | Default | Max | Description           |
|------------|--------|--------------------|---------|-----|-----------------------|
| `bv`       | string | yes                | —       | —   | BinaryView ID         |
| `address`  | string | one of addr/name   | —       | —   | Function address      |
| `name`     | string | one of addr/name   | —       | —   | Function name         |
| `depth`    | int    | no                 | 3       | 10  | Max BFS depth         |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "target": "_memcpy",
    "max_depth": 5,
    "edges": [
      {
        "caller": "_parse_header",
        "caller_addr": "0x100004100",
        "callee": "_memcpy",
        "callee_addr": "0x100007f00",
        "site": "0x100004150",
        "depth": 1
      },
      {
        "caller": "main",
        "caller_addr": "0x100003a40",
        "callee": "_parse_header",
        "callee_addr": "0x100004100",
        "site": "0x100003a80",
        "depth": 2
      }
    ]
  }
}
```

Each edge in `edges` represents a caller→callee relationship:

| Field        | Description                                      |
|--------------|--------------------------------------------------|
| `caller`     | Name of the calling function                     |
| `caller_addr`| Address of the calling function                  |
| `callee`     | Name of the called function                      |
| `callee_addr`| Address of the called function                   |
| `site`       | Address of the call instruction                  |
| `depth`      | Distance from the target (1 = direct caller)     |

This is useful for answering reachability questions: "Can an attacker reach this dangerous function from an external entry point?"

### Data and types

#### `strings`

List strings found in the binary with optional filtering.

```bash
# All strings (first 20)
curl -s -X POST http://localhost:13337/cmd/strings \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","limit":20}'

# Filter by content
curl -s -X POST http://localhost:13337/cmd/strings \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","filter":"error","limit":50}'

# Only strings >= 8 characters
curl -s -X POST http://localhost:13337/cmd/strings \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","min_length":8,"limit":100}'
```

**Parameters:**

| Parameter    | Type   | Required | Default | Max  | Description                    |
|--------------|--------|----------|---------|------|--------------------------------|
| `bv`         | string | yes      | —       | —    | BinaryView ID                  |
| `filter`     | string | no       | `""`    | —    | Case-insensitive substring     |
| `limit`      | int    | no       | 200     | 5000 | Max results                    |
| `offset`     | int    | no       | 0       | —    | Skip results                   |
| `min_length` | int    | no       | 4       | —    | Minimum string length          |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "total": 1500,
    "offset": 0,
    "limit": 20,
    "strings": [
      {"address": "0x100006000", "length": 12, "value": "Error: %s\n"},
      {"address": "0x100006010", "length": 25, "value": "Connection refused: %s:%d"}
    ]
  }
}
```

#### `variables`

List parameters and local variables of a function, with their types.

```bash
curl -s -X POST http://localhost:13337/cmd/variables \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","name":"_parse_header"}'
```

**Parameters:**

| Parameter  | Type   | Required           | Description            |
|------------|--------|--------------------|------------------------|
| `bv`       | string | yes                | BinaryView ID          |
| `address`  | string | one of addr/name   | Function address       |
| `name`     | string | one of addr/name   | Function name          |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "function": "_parse_header",
    "address": "0x100004100",
    "parameters": [
      {"name": "arg1", "type": "char*"},
      {"name": "arg2", "type": "int64_t"}
    ],
    "locals": [
      {"name": "var_80", "type": "char [128]", "source": "StackVariableSourceType"},
      {"name": "var_8", "type": "int64_t", "source": "StackVariableSourceType"}
    ]
  }
}
```

The `source` field indicates where the variable was identified from:

| Source                      | Meaning                          |
|-----------------------------|----------------------------------|
| `StackVariableSourceType`   | Variable on the stack            |
| `RegisterVariableSourceType`| Variable in a register           |
| `FlagVariableSourceType`    | CPU flags-based variable         |

#### `types`

List named types (structs, enums, typedefs) defined in the binary analysis.

```bash
curl -s -X POST http://localhost:13337/cmd/types \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","filter":"header","limit":20}'
```

**Parameters:**

| Parameter | Type   | Required | Default | Max | Description                    |
|-----------|--------|----------|---------|-----|--------------------------------|
| `bv`      | string | yes      | —       | —   | BinaryView ID                  |
| `filter`  | string | no       | `""`    | —   | Substring filter on type name  |
| `limit`   | int    | no       | 50      | 500 | Max results                    |
| `offset`  | int    | no       | 0       | —   | Skip results                   |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "total": 45,
    "offset": 0,
    "limit": 20,
    "types": [
      {"name": "packet_header_t", "definition": "struct packet_header_t __packed\n{\n    uint32_t magic;\n    uint16_t version;\n    uint16_t length;\n    uint8_t data[0]\n}", "width": 8}
    ]
  }
}
```

| Field       | Description                                        |
|-------------|----------------------------------------------------|
| `name`      | Type name                                          |
| `definition`| Full type definition as text                       |
| `width`     | Size of the type in bytes                          |

### Raw data

#### `read_bytes`

Read raw bytes from a specific address.

```bash
curl -s -X POST http://localhost:13337/cmd/read_bytes \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100006000","length":64}'
```

**Parameters:**

| Parameter | Type   | Required | Default | Max  | Description                    |
|-----------|--------|----------|---------|------|--------------------------------|
| `bv`      | string | yes      | —       | —    | BinaryView ID                  |
| `address` | string | yes      | —       | —    | Start address                  |
| `length`  | int    | no       | 256     | 4096 | Number of bytes to read        |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "address": "0x100006000",
    "length": 64,
    "hex": "48656c6c6f20576f726c6421...",
    "base64": "SGVsbG8gV29ybGQh...",
    "comment": "some comment (if exists)"
  }
}
```

The data is returned in two encodings: `hex` (hexadecimal string) and `base64`. Use whichever is more convenient for your tooling.

**Error:** `"Can't read data from the address 0x..."` — the address is unmapped or outside any loaded segment. Verify the address against `sections` output.

### Comments

#### `get_comment`

Read comments at a specific address.

```bash
curl -s -X POST http://localhost:13337/cmd/get_comment \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40"}'
```

**Parameters:**

| Parameter | Type   | Required | Description            |
|-----------|--------|----------|------------------------|
| `bv`      | string | yes      | BinaryView ID          |
| `address` | string | yes      | Address to check       |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "address": "0x100003a40",
    "function": "main",
    "func_comment": "TODO: verify input length",
    "bv_comment": "global analysis note"
  }
}
```

| Field          | Presence                         | Description                          |
|----------------|----------------------------------|--------------------------------------|
| `function`     | if address is inside a function  | Name of the containing function      |
| `func_comment` | if a function-level comment exists | The function-level comment text      |
| `bv_comment`   | if a BV-level comment exists     | The BinaryView-level comment text    |

If no comments exist at the address, only `bv` and `address` are returned.

#### `set_comment`

Write, append to, or delete a comment at a specific address.

```bash
# Set a function-level comment (default)
curl -s -X POST http://localhost:13337/cmd/set_comment \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40","comment":"checked: no overflow here"}'

# Append to an existing comment
curl -s -X POST http://localhost:13337/cmd/set_comment \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40","comment":"also verified return value","append":true}'

# Set a BinaryView-level comment (for data addresses or outside functions)
curl -s -X POST http://localhost:13337/cmd/set_comment \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100008000","comment":"vtable for Parser class","level":"bv"}'

# Delete a comment (set to empty string)
curl -s -X POST http://localhost:13337/cmd/set_comment \
  -H "Content-Type: application/json" \
  -d '{"bv":"0","address":"0x100003a40","comment":""}'
```

**Parameters:**

| Parameter | Type   | Required | Default      | Description                         |
|-----------|--------|----------|--------------|-------------------------------------|
| `bv`      | string | yes      | —            | BinaryView ID                       |
| `address` | string | yes      | —            | Target address                      |
| `comment` | string | yes      | —            | Comment text (empty string to delete)|
| `level`   | string | no       | `"function"` | `"function"` or `"bv"`              |
| `append`  | bool   | no       | `false`      | Append to existing instead of replacing |

**Response:**

```json
{
  "ok": true,
  "data": {
    "bv": "0",
    "address": "0x100003a40",
    "function": "main",
    "level": "function",
    "comment": "checked: no overflow here\nalso verified return value"
  }
}
```

**Error:** `"No function contains 0x..."` — the address is not inside any recognized function. Use `"level":"bv"` to set a BinaryView-level comment instead.

**Tip:** comments are saved in the Binary Ninja database (`.bndb`). Don't forget to save your project in BN to persist them.

## Error handling

### Common errors

| HTTP | Error message                                 | Meaning                                     | Solution                                |
|------|-----------------------------------------------|---------------------------------------------|-----------------------------------------|
| 404  | `unknown command: <name>`                     | Unrecognized command name                   | Check spelling; use `GET /cmd` for list |
| 500  | `Missing required parameter 'bv'`             | No `"bv"` in request body                   | Add `"bv":"<id>"` to the JSON           |
| 500  | `Unknown BinaryView id=<id>`                  | The ID doesn't exist                        | Run `list_views` to see valid IDs       |
| 500  | `BinaryView id for '...' is no longer valid`  | File was closed in BN                       | Reopen file; get new ID from `list_views` |
| 500  | `No function at 0x...`                        | No function at or containing this address   | Verify address; maybe create function manually in BN (press `P`) |
| 500  | `No function named '...'`                     | Name not found across all name forms        | Try partial name via `functions` with `filter` |
| 500  | `HLIL unavailable for <name>`                 | BN couldn't decompile this function         | Use `disasm` instead                    |
| 500  | `Can't read data from the address 0x...!`     | Address is unmapped                         | Verify against `sections` output        |
| 500  | `No function contains 0x...`                  | Address not inside any function (for `set_comment`) | Use `"level":"bv"` |

### Connection errors

If `curl` reports connection refused or timeout:

1. Is Binary Ninja running?
2. Is a file open? (The server starts only when a file is opened.)
3. Is the port correct? (Default is `13337`.)
4. Is Binary Ninja frozen? (Check the UI.)

## Configuration

### Port and bind address

The server defaults to `127.0.0.1:13337`. To change this, call `start()` manually **before** opening a file, or call `stop()` and `start()` with different parameters:

```py
# In Binary Ninja console:
import hobo_bn_mcp

hobo_bn_mcp.stop()
hobo_bn_mcp.start("0.0.0.0", 9999)  # listen on all interfaces, port 9999
```

**Security warning:** binding to `0.0.0.0` exposes your Binary Ninja analysis to the network. Only do this on trusted networks.

### Debug logging

To enable debug-level logging (including per-request logs), set the flag before the server starts:

```py
import hobo_bn_mcp
hobo_bn_mcp.LOG_DEBUG_MSG = True
hobo_bn_mcp.start()
```

## Troubleshooting

### "Server doesn't start when I open a file"

- Check the Binary Ninja Log console for errors.
- Make sure `hobo_bn_mcp.py` is in the correct plugins directory.
- Make sure there are no syntax errors — try `import hobo_bn_mcp` manually in the BN console.

### "list_views returns an empty list"

- Binary Ninja may still be analyzing the file. Wait for analysis to complete (progress bar at the bottom of BN window).
- The plugin filters out raw views (views with no architecture). If your file failed analysis, it may not have a proper view.

### "BinaryView ID 0 doesn't work"

- In older versions, the first view registered might have been a "Raw" view. Version 2.0.0 filters these out automatically. Make sure you have the latest version of the plugin.
- Run `list_views` to see the actual available IDs — the first valid ID might be `"0"` or higher.

### "decompile returns empty code"

- Binary Ninja analysis may not have completed. Wait for the progress bar to finish.
- The function may be too small or contain only data. Try `disasm` instead.
- Try running `bv.update_analysis_and_wait()` in the BN console.

### "Comments don't appear in Binary Ninja UI"

- Function-level comments appear in the Linear View and Graph View in BN.
- BV-level comments appear in the Linear View.
- Make sure you're looking at the correct address and view in BN.

### "Server becomes unresponsive"

- Binary Ninja itself may be busy (running analysis, loading a large file).
- The server runs in daemon threads — if BN's Python interpreter is blocked, requests will queue.
- Try `ping` — if it responds, the server is alive but a previous command may be slow.

## Limitations

- **Read-only + comments.** The server cannot rename functions, change types, patch bytes, or modify the binary in any way other than setting comments.
- **No default BinaryView.** Every command must specify `"bv"`. This is by design — the user may switch tabs in Binary Ninja at any time, and an implicit default would lead to silent errors.
- **Threading.** Commands execute in background threads, not BN's main thread. This is safe for all read operations and comments. If write operations (rename, retype) are added in the future, they would need `execute_on_main_thread_and_wait()`.
- **Single server instance.** Only one server can run per Binary Ninja process. Multiple BN windows share the same server and view registry.
- **IDs are not reused.** Closed views keep their IDs permanently. In very long sessions with many open/close cycles, IDs may reach high numbers — this is normal.
- **Large responses.** Some commands can return very large JSON responses (e.g. `functions` with no filter on a binary with 100k+ functions). Always use `limit` and `filter` parameters.
- **No authentication.** The server has no authentication or authorization. Anyone who can reach the IP/port can read your analysis and modify comments. Keep it on localhost or a trusted network.