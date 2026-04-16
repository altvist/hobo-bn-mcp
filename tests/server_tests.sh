#!/bin/bash
# -------------------------------------------------------
# HOBO BN MCP v2 — smoke test (curl)
# Run while the server is up in Binary Ninja.
# Adjust placeholders below to match your binary.
# -------------------------------------------------------

# --- Placeholders: edit these to match your binary ------
HOST="127.0.0.1"
PORT="13337"
BASE="http://${HOST}:${PORT}"

BV="1" # BinaryView ID from list_views
FUNC_NAME="DGifOpenFileName"
FUNC_ADDR="0x423e94"
IMPORT_FILTER="mem"
STRING_FILTER="error"
READ_ADDR="0x423e94"
READ_LEN=64
COMMENT_ADDR="0x423ea8"
# ---------------------------------------------------------

OK=0
FAIL=0

run() {
    local label="$1"; shift
    printf "\n\033[1;34m=== %s ===\033[0m\n" "$label"
    printf "\033[0;36m> %s\033[0m\n" "$*"

    if output=$("$@" 2>&1); then
        if command -v python3 &>/dev/null; then
            echo "$output" | python3 -m json.tool 2>/dev/null || echo "$output"
        else
            echo "$output"
        fi

        if echo "$output" | grep -q '"ok":true\|"ok": true'; then
            printf "\033[0;32m✓ PASS\033[0m\n"
            OK=$((OK + 1))
        else
            printf "\033[0;31m✗ FAIL (ok!=true)\033[0m\n"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "$output"
        printf "\033[0;31m✗ FAIL (curl error)\033[0m\n"
        FAIL=$((FAIL + 1))
    fi
}

run_expect_error() {
    local label="$1"; shift
    printf "\n\033[1;34m=== %s (expect error) ===\033[0m\n" "$label"
    printf "\033[0;36m> %s\033[0m\n" "$*"

    output=$("$@" 2>&1) || true

    if command -v python3 &>/dev/null; then
        echo "$output" | python3 -m json.tool 2>/dev/null || echo "$output"
    else
        echo "$output"
    fi

    if echo "$output" | grep -q '"ok":false\|"ok": false'; then
        printf "\033[0;32m✓ PASS (got expected error)\033[0m\n"
        OK=$((OK + 1))
    else
        printf "\033[0;33m⚠ UNEXPECTED (expected error but got ok)\033[0m\n"
        FAIL=$((FAIL + 1))
    fi
}

H="Content-Type: application/json"

# ------ Meta (no bv) ------

run "ping" \
    curl -s "$BASE/cmd/ping"

run "version" \
    curl -s "$BASE/cmd/version"

run "command list" \
    curl -s "$BASE/cmd"

run "list_views" \
    curl -s "$BASE/cmd/list_views"

# ------ Orientation ------

run "binary_info" \
    curl -s -X POST "$BASE/cmd/binary_info" \
    -H "$H" -d "{\"bv\":\"${BV}\"}"

run "sections" \
    curl -s -X POST "$BASE/cmd/sections" \
    -H "$H" -d "{\"bv\":\"${BV}\"}"

run "imports (all)" \
    curl -s -X POST "$BASE/cmd/imports" \
    -H "$H" -d "{\"bv\":\"${BV}\"}"

run "imports (filtered)" \
    curl -s -X POST "$BASE/cmd/imports" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"filter\":\"${IMPORT_FILTER}\"}"

run "exports" \
    curl -s -X POST "$BASE/cmd/exports" \
    -H "$H" -d "{\"bv\":\"${BV}\"}"

# ------ Function navigation ------

run "functions (first 10)" \
    curl -s -X POST "$BASE/cmd/functions" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"limit\":10}"

run "functions (filtered)" \
    curl -s -X POST "$BASE/cmd/functions" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"filter\":\"${FUNC_NAME}\",\"limit\":5}"

run "decompile by name" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"name\":\"${FUNC_NAME}\"}"

run "decompile by address" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${FUNC_ADDR}\"}"

run "disasm by name" \
    curl -s -X POST "$BASE/cmd/disasm" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"name\":\"${FUNC_NAME}\"}"

run "disasm by address" \
    curl -s -X POST "$BASE/cmd/disasm" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${FUNC_ADDR}\"}"

# ------ Cross-references ------

run "xrefs_to" \
    curl -s -X POST "$BASE/cmd/xrefs_to" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${FUNC_ADDR}\"}"

run "xrefs_from by name" \
    curl -s -X POST "$BASE/cmd/xrefs_from" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"name\":\"${FUNC_NAME}\"}"

run "callers (depth=2)" \
    curl -s -X POST "$BASE/cmd/callers" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"name\":\"${FUNC_NAME}\",\"depth\":2}"

# ------ Data & types ------

run "strings (first 10)" \
    curl -s -X POST "$BASE/cmd/strings" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"limit\":10}"

run "strings (filtered)" \
    curl -s -X POST "$BASE/cmd/strings" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"filter\":\"${STRING_FILTER}\",\"limit\":10}"

run "variables" \
    curl -s -X POST "$BASE/cmd/variables" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"name\":\"${FUNC_NAME}\"}"

run "types (first 10)" \
    curl -s -X POST "$BASE/cmd/types" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"limit\":10}"

# ------ Raw data ------

run "read_bytes" \
    curl -s -X POST "$BASE/cmd/read_bytes" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${READ_ADDR}\",\"length\":${READ_LEN}}"

# ------ Comments ------

run "set_comment" \
    curl -s -X POST "$BASE/cmd/set_comment" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${COMMENT_ADDR}\",\"comment\":\"[hobo-test] looks suspicious\"}"

run "set_comment (append)" \
    curl -s -X POST "$BASE/cmd/set_comment" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${COMMENT_ADDR}\",\"comment\":\"possible OOB read\",\"append\":true}"

run "get_comment" \
    curl -s -X POST "$BASE/cmd/get_comment" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${COMMENT_ADDR}\"}"

run "decompile (verify comment in output)" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${COMMENT_ADDR}\"}"

run "set_comment (clear)" \
    curl -s -X POST "$BASE/cmd/set_comment" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${COMMENT_ADDR}\",\"comment\":\"\"}"

run "get_comment (should be empty)" \
    curl -s -X POST "$BASE/cmd/get_comment" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"${COMMENT_ADDR}\"}"

# ------ Error handling ------

run_expect_error "missing bv parameter" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"name\":\"main\"}"

run_expect_error "unknown bv id" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"bv\":\"999\",\"name\":\"main\"}"

run_expect_error "bad address" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"0xDEADDEADDEADDEAD\"}"

run_expect_error "bad function name" \
    curl -s -X POST "$BASE/cmd/decompile" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"name\":\"this_function_does_not_exist_12345\"}"

run_expect_error "unknown command" \
    curl -s "$BASE/cmd/nonexistent"

run_expect_error "read unmapped address" \
    curl -s -X POST "$BASE/cmd/read_bytes" \
    -H "$H" -d "{\"bv\":\"${BV}\",\"address\":\"0xFFFFFFFFFFFFFFFF\",\"length\":16}"

# ------ Summary ------

printf "\n\033[1;37m============================\033[0m\n"
printf "\033[1;32m  PASS: %d\033[0m\n" "$OK"
printf "\033[1;31m  FAIL: %d\033[0m\n" "$FAIL"
printf "\033[1;37m============================\033[0m\n"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi