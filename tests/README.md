# Before run `server_tests.sh` 

1. Install HOBO BN MCP (check [User Guide](../user_guide.md))

2. Run Binary Ninja and open some reverse engineering project(s)

3. Open `server_tests.sh` and edit the placeholders at the beginning of the file:

    ```sh
    # --- Placeholders: edit these to match your binary ------
    HOST="127.0.0.1"
    PORT="13337"
    BASE="http://${HOST}:${PORT}"

    BV="1" # BinaryView ID from list_views
    FUNC_NAME="NextAudioFile::IsDataFormatSupported"
    FUNC_ADDR="0x1830faa14"
    IMPORT_FILTER="mem"
    STRING_FILTER="error"
    READ_ADDR="0x1830faa2c"
    READ_LEN=64
    COMMENT_ADDR="0x1830faa14"
    # ---------------------------------------------------------
    ```

Now, you can run `server_tests.sh` on any vm or host that can "see" the `http://${HOST}:${PORT}` you specified. The expected output:

```
=== ping ===
> curl -s http://127.0.0.1:13337/cmd/ping
{
    "ok": true,
    "data": {
        "status": "pong"
    }
}
✓ PASS

=== version ===
> curl -s http://127.0.0.1:13337/cmd/version
{
    "ok": true,
    "data": {
        "binary_ninja_version": "5.3.9434 Personal",
        "hobo_mcp_version": "v1.1.0"
    }
}
✓ PASS

=== command list ===
> curl -s http://127.0.0.1:13337/cmd
{
    "ok": true,
    "data": {
        "commands": [
            "binary_info",
            "callers",
            "decompile",
            "disasm",
            "exports",
            "functions",
            "get_comment",
            "imports",
            "list_views",
            "ping",
            "read_bytes",
            "sections",
            "set_comment",
            "strings",
            "types",
            "variables",
            "version",
            "xrefs_from",
            "xrefs_to"
        ]
    }
}
✓ PASS

=== list_views ===
> curl -s http://127.0.0.1:13337/cmd/list_views
{
    "ok": true,
    "data": {
        "views": [
            {
                "id": "0",
                "filename": "~/temp/max_libs/arm64-v8a/libstatic-webp.so.bndb",
                "path": "~/temp/max_libs/arm64-v8a/libstatic-webp.so.bndb",
                "arch": "aarch64",
                "platform": "linux-aarch64",
                "status": "ready"
            },
            {
                "id": "1",
                "filename": "~/temp/dyld_shared_cache_arm64e.bndb",
                "path": "~/temp/dyld_shared_cache_arm64e.bndb",
                "arch": "aarch64",
                "platform": "mac-aarch64",
                "status": "ready"
            },
            {
                "id": "2",
                "filename": "/usr/libexec/audiomxd",
                "path": "/usr/libexec/audiomxd",
                "arch": "aarch64",
                "platform": "mac-aarch64",
                "status": "ready"
            }
        ]
    }
}
✓ PASS

...more tests...

=== unknown command (expect error) ===
> curl -s http://127.0.0.1:13337/cmd/nonexistent
{
    "ok": false,
    "error": "unknown command: nonexistent"
}
✓ PASS (got expected error)

=== read unmapped address (expect error) ===
> curl -s -X POST http://127.0.0.1:13337/cmd/read_bytes -H Content-Type: application/json -d {"bv":"1","address":"0xFFFFFFFFFFFFFFFF","length":16}
{
    "ok": false,
    "error": "Can't read data from the address 0xffffffffffffffff!"
}
✓ PASS (got expected error)

============================
  PASS: 35
  FAIL: 0
============================
```
