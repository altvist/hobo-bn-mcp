# HOBO BN MCP

Installation:

1. Locate your Binary Ninja plugins directory:

   | OS      | Path                                                  |
   |---------|-------------------------------------------------------|
   | macOS   | `~/Library/Application Support/Binary Ninja/plugins/` |
   | Linux   | `~/.binaryninja/plugins/`                             |
   | Windows | `%APPDATA%\Binary Ninja\plugins\`                     |

2. Copy `hobo_bn_mcp.py` into that directory.

3. Restart Binary Ninja

4. Verify from a terminal:

   ```bash
   curl -s http://localhost:13337/cmd/ping
   ```

   Expected response: `{"ok":true,"data":{"status":"pong"}}`

Read [User Guide](../claude-code-docker-setup/workspace/user_guide.md) and [Claude Code in Docker + HOBO BN MCP](../claude-code-docker-setup/README.md)

Have fun!