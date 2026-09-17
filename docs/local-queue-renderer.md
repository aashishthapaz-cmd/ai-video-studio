# Local queue renderer

Scheduled rendering and Facebook publishing run on this PC. GitHub Actions no
longer renders queued videos because it cannot access this PC's ComfyUI. The
queue and publication history are local-only and are never committed or pushed.

## Start

Run `Start Local Queue Renderer.bat` (or the renamed `Start Cloud Video
Generator.bat`) once. It opens the local studio at `http://127.0.0.1:8190` and
starts a scheduler that checks `cloud_generator/jobs_queue.json` every 15
seconds. Keep the PC awake and the renderer running for scheduled posts.

## Local secrets

Copy the relevant values from `.env.example` into the ignored `.env` file.
`FACEBOOK_PAGES_JSON` is the local source of truth for Page IDs and Page Access
Tokens. The local settings file is also ignored, so saving a page through the
studio UI cannot add its token to Git.

Before enabling scheduled posts, use the studio's **Test Page** action to verify
each Page ID and Page Access Token. Queued jobs use their target page IDs and
the publisher refuses an unmatched target, preventing accidental cross-posting.
If a valid local credential is missing, the renderer leaves the job pending and
does not render or remove it.

## Git queue changes

Rendering output, local settings, tokens, page configuration, queue entries,
publication history, and job media are ignored by Git.
