# Project Guidelines

Rules for this project only, written by people or AI agents. They add to AIKit's principles and
rank below them: a guideline never overrides a principle (PRINCIPLE-000 R6, PRINCIPLE-001 R4).
Add one with `python aikit.py guideline <name> "<rule>" --source <user|ADR-NNN|person>`, or by
hand as one line below in the form `- **G-NNN** (source): rule`; IDs are never reused.

Persisted state carries a format version. A loader refuses a version it does not support,
without modifying or quarantining that file; older versions migrate when a migration exists.

## Rules
- **G-001** (user): Graphics review workflow: delegate every visual/ASCII-rendering analysis to the task tool with subagent_type=general, model=qwen3-vl-30b, provider=evren2 and no reasoning variant (that model rejects one). Brief it with absolute paths under projects/aldervale, point it at the current .inspect/*.png frames plus render.py, mesh.py, atlas.py, buffer.py and models.py, and require a read-only, evidence-backed ranked report (<=1600 words) before any edit. Regenerate the frames with 'python -m aldervale --inspect .inspect' first. If the child starts in the workspace root and reports missing files, resume its task_id with the absolute project paths. The main session owns edits, tests, checks and commits.
- **G-002** (user): Vision-review fallback (supersedes G-001's provider choice): try qwen3-vl-30b on evren2, then evren3, evren4 and evren5 with no reasoning variant. If a provider returns a daily-token or quota error, use the free Kilo vision model 'NVIDIA: Nemotron 3.5 Super VL (free)' with provider kilo and the thinking variant, or another Kilo Qwen3-VL model. Treat quota exhaustion as a temporary blocker, not a failed review: resume the same task_id or start a fresh read-only review with the same absolute image paths. Reviews stay read-only and must cite image evidence; the main session still verifies claims against frames and code and owns edits, tests and gates.
- **G-003** (ADR-019): Image-review providers must demonstrate that they can read an image before their ratings are trusted. In this harness qwen3-vl-30b on evren3 and the free Kilo 'NVIDIA: Nemotron 3.5 Super VL (free)' return PNGs as binary and cannot see them; their visual ratings are invalid and must be discarded. Verify model changes structurally from Studio data (DOM text and colours, sprite grids, mesh vertex bounds, geometry arithmetic) and treat the Studio page as the human visual check. If no provider proves image reading, state that no visual review was performed instead of claiming one.
