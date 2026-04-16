# HOBO BN MCP

## What is HOBO BN MCP?

HOBO BN MCP is a single Python script with zero external dependencies. Despite its name, it is _not_ an MCP (Model Context Protocol) server. Instead, HOBO BN MCP uses a simple JSON-over-HTTP protocol.

It runs inside [Binary Ninja](https://binary.ninja/) as a plugin. It works with _any_ Binary Ninja license and exposes Binary Ninja's analysis capabilities — decompilation, disassembly, cross-references, type information, and more — over HTTP. This allows you to interact with reverse engineering projects from the command line, scripts, LLM agents, or any HTTP client.

## How to use HOBO BN MCP?

If you want to use HOBO BN MCP yourself, read the [User Guide](./claude-code-docker-setup/user_guide.md).

If you want to teach Claude how to use HOBO BN MCP from the command line, add the ["Binary Ninja integration"](./claude-code-docker-setup/CLAUDE.md) section to your `CLAUDE.md` (make sure to specify the correct path to `user_guide.md` so Claude Code can find it).

## HOBO BN MCP vs. "true MCP" solutions

Advantages:

- Unlike "true MCP" solutions, HOBO BN MCP does not inject full tool descriptions (name, parameters, JSON Schema, description) into the context with every message. With 19 commands, "true MCP" solutions can waste 2–3K tokens per request, even if you're just asking Claude: _"hi! how are you?"_

- Unlike some "true MCP" solutions, HOBO BN MCP does not require Binary Ninja headless mode, so you don’t necessarily have to buy a [commercial Binary Ninja license for \$1499+](https://binary.ninja/purchase/#commercial). Even the [\$74 student license](https://binary.ninja/purchase/#non-commercial) is sufficient to run HOBO BN MCP.

- Easier debugging: `curl localhost:13337/cmd/ping` vs. tracing JSON-RPC over an `stdio` pipe.

- Lightweight, fast, and dependency-free.

However, HOBO BN MCP has one significant limitation: you must manually load your projects in Binary Ninja and keep them open the entire time Claude is working with them.

This is not a problem for Claude-assisted manual research — Binary Ninja is usually open anyway because you need to see the code. But if you want full headless automation like _"here's a directory, open and analyze each file in it, find binary vulnerabilities"_, you'll probably still need to [pay \$1499+ for a headless-capable license](https://binary.ninja/purchase/#commercial), use a "true MCP" solution, and be ready to spend more tokens.

That's it!
