# claude-vox

Claude Code talks you through its work, in its own words.

The moment Claude starts working on something, `claude-vox` speaks the line it
opens with -- *"I'll dig into how the timezone dropdown is rendered"* --
so you hear it start, not just finish. When the turn ends, it speaks a one- or
two-sentence summary of what actually happened, written by Claude to be heard.

```
● I'll dig into how the timezone dropdown is rendered.        <- spoken live
     Searched for 5 patterns, ran 5 shell commands
● Diagnosis confirmed: the API sends a display label but the
     dropdown keys on date codes, so Radix renders blank.
     Ran 4 shell commands
● Done, Sir. Fixed in TimezonePicker.tsx. Root cause...
     [ a screen of code, paths, and a verification table ]

  🔊 Fixed the timezone dropdown, Sir -- it was matching     <- spoken at the end
     on the wrong key, so the saved value showed blank. Verified
     across every screen that uses it.
```

Spoken, seconds apart: *"I'll dig into how the timezone dropdown is
rendered."* ... then, at the end, *"Fixed the timezone dropdown, Sir -- it
was matching on the wrong key, so the saved value showed blank. Verified across
every screen that uses it."* Everything in between -- the code, the paths, the table --
is never read aloud.

## Why it works this way

Most Claude Code TTS tools read the whole response (long, and full of paths and
punctuation nobody wants to hear aloud) or wait until the very end to say
anything. `claude-vox` does neither. Two things make it feel like an assistant
rather than a screen reader:

- **A live intro.** Claude Code has no hook that fires mid-stream, but it *does*
  write each message to the transcript as the turn runs. So when you submit a
  prompt, vox starts watching that file and speaks Claude's first line the
  instant a tool call shows work has begun -- often a minute or more before the
  turn ends. A quick reply with no tools skips the intro and is spoken once, at
  the end.
- **A summary, not a slice.** The closing line is Claude's own spoken summary of
  the *whole* turn -- the important part is usually in the middle, which reading
  the last paragraph would miss. Claude writes it on a `🔊` line, and a
  speakable filter strips anything that would read like a terminal (`npx tsc
  --noEmit`, `src/utils/optionKeys.ts`, `localhost:3000`) before it is voiced.

## Install

```bash
git clone https://github.com/Ishan-sa/claude-vox.git
cd claude-vox
./install.sh
```

Requirements: `python3` (3.8+) and a way to make sound. Nothing else -- the
whole thing is standard library, no pip install, no dependencies.

The installer copies the code to `~/.claude/vox/`, registers three hooks in
`~/.claude/settings.json` (backing up the old file first), installs the `/vox`
slash command, and writes a config tuned to whatever it finds on your machine.

**Restart Claude Code before this takes effect.** Hooks are read once, at
startup -- any session that was already open when you installed will stay
silent until you reopen it. This is the most common "installed but nothing
speaks" surprise.

Then, in a fresh session, turn it on:

```
/vox on
```

`/vox off` to stop, `/vox status` to see what is configured, `/vox test` to
hear a line right now without enabling anything, `/vox opener off` to silence
the instant acknowledgement while leaving the rest speaking.

The voice you get out of the box is whatever your OS ships -- clear enough, but
plainly synthetic. For a neural one, see [a better voice](#a-better-voice)
below; it is one extra command and still needs no API key.

To remove it: `./uninstall.sh` (add `--purge` to delete the config too).

## How it works

Three hooks, all of which exit 0 no matter what goes wrong -- a broken speaker
must never wedge a coding session.

| Hook | What it does |
|---|---|
| `SessionStart` | If enabled, asks the session to end replies with a spoken `🔊` summary line, so the convention survives restarts |
| `UserPromptSubmit` | Kills playback the instant you type again; in assistant mode, starts the watcher that speaks Claude's first working line live |
| `Stop` | Reads the transcript and speaks the summary once the turn ends |

Both the live intro and the end-of-turn summary run in detached workers that
outlive the hook, so submitting a prompt is never blocked on speech. Subagent
output is ignored -- only what you actually see on screen gets spoken.

### Speaking modes

`speech_mode` in config chooses what to read:

| Mode | Speaks |
|---|---|
| `assistant` *(default)* | Claude's live opening line as it starts working, then its own `🔊` summary of the whole turn at the end |
| `bookends` | The first and last paragraph, read as one line |
| `intro` | Just the opening paragraph |
| `summary` | Just the closing paragraph |
| `marker` | Only a line the model prefixes with the marker (below) |

`assistant` and `marker` ask the model (via `SessionStart`) to write its own
spoken summary on a `🔊` line; the other modes read the prose as written and
inject nothing. In every mode a `🔊` line, if present, is what gets spoken --
an override for dictating the words precisely. In assistant mode the live intro
can be turned off on its own with `live_intro: false`. `segment_chars` caps how
long a spoken line may be before it is trimmed at a sentence boundary.

### The instant opener (optional, off by default)

If you also want a sound the *instant* you hit enter -- before Claude has
written anything -- turn on the opener. It speaks a short phrase from a cache,
so it plays with no delay and never holds up your prompt. It is off by default
because the intro paragraph already gives a content-aware opening; enable it
only if you want that extra immediate ack.

**No phrases ship with it.** Whatever it says, you wrote -- a stock line you did
not choose, announcing every single turn, wears out fast, and tracking down
where it came from is worse. Give it words and it speaks; leave it empty and it
stays quiet whatever the switch says.

```json
{ "opener": { "enabled": true, "phrases": ["On it.", "Working on it."] } }
```

`/vox opener on` and `/vox opener off` flip it without opening the file.


## A better voice

The stock voices are the ones your operating system already had. They are
intelligible and they are free, and after an hour of listening to one narrate
your work you will want something else.

```bash
./setup-edge-tts.sh                      # en-GB-RyanNeural, a British male
./setup-edge-tts.sh en-US-GuyNeural      # or name any voice you like
./setup-edge-tts.sh --opener             # and pre-render your opener phrases
```

This reaches Microsoft's neural voices through `edge-tts`. No API key, no
account, no per-word billing. It is the only dependency this project has, and
it goes into its own virtualenv under `~/.claude/vox/venv`, so nothing lands on
your system Python. `--list-voices` on that venv's `edge-tts` prints the
several hundred voices available.

It stays out of the way of the two things that actually matter in a hook:

**It is never the reason a turn goes quiet.** If the network is down, or
Microsoft is having a bad afternoon, or you deleted the venv, it speaks the
line through the offline OS voice instead. Worse audio beats no audio when the
point is to tell you something finished.

**It does not make you wait to be acknowledged.** Neural synthesis is a network
round-trip, which is fine at the end of a turn and far too slow for the opener
that fires the instant you press enter. So short lines are cached on disk by
voice, prosody and text: the setup script pre-renders your opener phrases, and
from then on they play immediately. Long lines are spoken once and never
repeated, so they are not worth caching and are cleaned up after playback.

Three environment variables tune it, should you want to:

| Variable | Default | Meaning |
|---|---|---|
| `VOX_RATE` | `-4%` | Speaking rate. Slightly slow reads as composed rather than chirpy |
| `VOX_PITCH` | `-4Hz` | Pitch shift. Slightly low puts some chest behind it |
| `VOX_FALLBACK_VOICE` | `Daniel` | The offline voice used when synthesis fails |

## Configuration

`~/.claude/vox/config.json`. Two backends cover essentially any setup.

### `command` -- hand the text to a CLI program

The default on most machines. The installer picks whichever of `say`,
`espeak-ng`, `espeak`, or `spd-say` it finds.

```json
{
  "backend": "command",
  "command": { "argv": ["say", "-v", "Daniel", "{text}"] }
}
```

`{text}` is replaced with the line to speak. Anything that synthesises from
argv works. `setup-edge-tts.sh` above is exactly this: it points `argv` at
`backends/edge-tts.sh`, which synthesises, plays, and caches. Piper works the
same way:

```json
{
  "backend": "command",
  "command": {
    "argv": ["sh", "-c", "echo '{text}' | piper -m en_US-ryan-high.onnx --output-raw | aplay -r 22050 -f S16_LE -t raw -"]
  }
}
```

### `http` -- POST to a TTS server

For neural voices from a local or remote server. Two response shapes are
supported.

**Server replies with a URL to the audio** (the default shape):

```json
{
  "backend": "http",
  "http": {
    "url": "http://127.0.0.1:5050/speak",
    "body": { "text": "{text}" },
    "audio_url_field": "url",
    "play_command": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{audio}"]
  }
}
```

**Server replies with raw audio bytes** -- set `audio_url_field` to `null` and
the body is written to a temp file, which `{audio}` then points at. This is the
OpenAI-compatible shape, so it works with OpenAI's TTS and every local server
that mimics it:

```json
{
  "backend": "http",
  "http": {
    "url": "https://api.openai.com/v1/audio/speech",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer sk-..."
    },
    "body": { "model": "gpt-4o-mini-tts", "voice": "onyx", "input": "{text}" },
    "audio_url_field": null,
    "play_command": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{audio}"]
  }
}
```

### Choosing a voice

With the `http` backend, whatever your TTS server accepts goes in `body`. The
default is a male British voice, `en-GB-RyanNeural`. Swap it for any voice your
server supports:

```json
{ "backend": "http", "http": { "body": { "text": "{text}", "voice": "en-US-GuyNeural" } } }
```

Some Jarvis-adjacent Edge TTS voices: `en-GB-RyanNeural` and `en-GB-ThomasNeural`
(British male), `en-US-GuyNeural` and `en-US-ChristopherNeural` (US male). With
the `command` backend the voice is a flag instead, e.g. `["say", "-v", "Daniel", "{text}"]`.

### Other settings

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | What `/vox on` and `/vox off` flip |
| `speech_mode` | `assistant` | What to read: `assistant`, `bookends`, `intro`, `summary`, or `marker` |
| `live_intro` | `true` | In assistant mode, speak Claude's first working line live. Set `false` for summary-only |
| `segment_chars` | `280` | Max length of each spoken line before it is trimmed |
| `marker` | `🔊` | The prefix that marks the spoken line. Change it if the emoji renders badly in your terminal |
| `max_chars` | `400` | Longer lines are truncated at a word boundary |
| `timeout` | `8` | Seconds to wait on the `http` backend |
| `opener.enabled` | `false` | Speak an extra short line the moment a prompt is submitted. `/vox opener on\|off` flips it; `/vox status` shows it |
| `opener.phrases` | *(empty)* | Your lines to rotate through; synthesised once, then cached. Nothing canned ships -- empty means silent |

## Troubleshooting

**Nothing is spoken.** Run `/vox status` -- if it says OFF, `/vox on`. If it
says ON, run `/vox test`: that isolates the audio path from the hook path. If
the test is silent, the backend is wrong; if the test works but real responses
are not spoken, the session started before the hooks were installed -- open a
fresh one.

**The intro never fires, only the summary.** The live intro speaks only when
Claude uses a tool -- a quick reply with no tools is spoken once, at the end.
It also needs a session started after install, since it rides the
`UserPromptSubmit` hook. Turn it off entirely with `live_intro: false`.

**Something says a stock phrase before every response.** That is the opener.
It is off by default and ships with no phrases, so both were set deliberately
at some point. `/vox opener off` silences it without touching anything else,
and `/vox status` shows where it stands.

**It speaks but the hooks never fire.** Hooks are read at startup -- restart
Claude Code after installing.

**It talks over itself.** It should not; each new line stops the previous one.
If it does, your `play_command` is spawning a player that detaches from its own
process group.

## License

MIT
