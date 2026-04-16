# Claude Code in Docker + HOBO BN MCP

> **Note!** This setup runs Claude Code inside a Docker container, with instructions on how to use HOBO BN MCP provided in [`CLAUDE.md`](./workspace/CLAUDE.md). It is intentionally minimal and provided as a working example. You can use it as a starting point for building your own more advanced and smarter setups.

To make it work:

1. Make sure you have a Pro (\$20/mo) or Max (\$100/mo) Claude plan.

2. Make sure you have Binary Ninja and Docker installed on your host.

3. [Install the HOBO BN MCP server](../server/README.md).

4. Build and start the Docker container:

    ```sh
    cd claude-code-docker-setup/
    ./build.sh
    ./up.sh
    ```

5. Follow the initial steps in the Docker console (you will need to complete Claude authorization, among other things). You only need to do this once. Next time just execute `./up.sh` in your terminal to start chatting with Claude.

6. Make sure your reverse engineering projects are open in Binary Ninja. 


Now you can ask Claude to analyse the code, for example:

```
> What binary ninja binary views do you see?

I need the HOBO BN MCP server IP and port before I can connect. 
What should I use? (Default is 127.0.0.1:13337)

> You are in a docker container on a macOS. Use http://host.docker.internal:13337

I see 2 open BinaryViews:
0 — libstatic-webp.so.bndb (aarch64, linux-aarch64)
1 — dyld_shared_cache_arm64e.bndb (aarch64, mac-aarch64) 

> Use view #1. Find `NextAudioFile::IsDataFormatSupported` method in the code. 

Found it: NextAudioFile::IsDataFormatSupported at 0x1830faa14, size 48 bytes. 
Want me to decompile it?

> Analyze it and tell me what .au file will NOT pass it? What actually is considered 
  as a valid Next Audio file?

It just delegates to MakeSNDSoundStruct. Let me look at that.

...

Now I have the full picture. Let me trace the logic and leave a comment 
on the function.

What this function actually does: Despite the name, it does not parse 
a .au file. It takes a Core Audio AudioStreamBasicDescription* and asks: 
"can this audio format be encoded into a NeXT/Sun .au (SND) file?" 
Success writes a populated SNDSoundStruct (magic .snd + header size 0x1c, 
sample rate, channels, and a format code) to arg2 and returns 0. Failure 
returns 'fmt?' (0x666d743f).

The accepted format matrix (format ID × bits × flags → SND format code):

┌───────────┬─────────────────┬────────────────────────┬───────────┐
│ mFormatID │ mBitsPerChannel │ Required mFormatFlags  │ SND code  │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ ulaw      │ any             │ —                      │ 1         │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ alaw      │ any             │ —                      │ 27 (0x1b) │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ lpcm      │ 8               │ !IsFloat               │ 2         │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ lpcm      │ 16              │ !IsFloat + IsBigEndian │ 3         │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ lpcm      │ 24              │ !IsFloat + IsBigEndian │ 4         │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ lpcm      │ 32              │ !IsFloat + IsBigEndian │ 5         │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ lpcm      │ 32              │ IsFloat + IsBigEndian  │ 6         │
├───────────┼─────────────────┼────────────────────────┼───────────┤
│ lpcm      │ 64              │ IsFloat + IsBigEndian  │ 7         │
└───────────┴─────────────────┴────────────────────────┴───────────┘

Everything else is rejected. Notably the code only inspects bits 0 
(kAudioFormatFlagIsFloat) and 1 (kAudioFormatFlagIsBigEndian) — IsSignedInteger 
and IsPacked are not checked.

What will NOT pass
  
1. Little-endian integer LPCM ≥ 16-bit — the most common form on modern platforms. 
16/24/32-bit LE PCM is rejected outright; only 8-bit PCM skips the endianness 
check (single byte).

2. Little-endian 32/64-bit float — same story for float.

3. LPCM with bit depths not in {8, 16, 24, 32} (integer) or not in {32, 64} (float). 
The integer path uses ror w10, #3 on bits−8, so anything that isn't a multiple 
of 8 or is > 32 bits falls into the "fmt?" path. 40/48/56-bit integer, 
2-bit, 20-bit — all rejected.

4. Any compressed / non-PCM format — AAC, MP3, Opus, FLAC, Apple Lossless, 
AC-3, etc. Only the three mFormatID values lpcm/ulaw/alaw reach the success path.

5. Float integer bit depth — e.g. IsFloat set with 16 bits or 24 bits is rejected
(float branch only accepts 32 or 64).

Bottom line on "valid Next Audio file": in NeXT .au (.snd) terms the function
enumerates exactly the classic set — μ-law, A-law, and signed big-endian linear
PCM at 8/16/24/32-bit, plus big-endian IEEE 32/64-bit float. Any .au file whose 
stored dataFormat isn't one  of codes {1, 2, 3, 4, 5, 6, 7, 27} would not be 
producible through this code path, and any ASBD presented to IsDataFormatSupported 
that falls outside the table above is rejected.

Let me drop a [claude] analysis comment on the function.   
```

To end your chat for now, just execute `/exit` in Claude console. Run `./up.sh` and go on as soon as you're ready to continue.