# Release Checklist

## Structure

- [ ] `src/` contains runnable source code.
- [ ] `assets/` contains logo and visual assets.
- [ ] `docs/` contains product and technical notes.
- [ ] `README.md` explains what SpringPaper is and how to run it.
- [ ] `CHANGELOG.md` records the release.
- [ ] `requirements.txt` lists only actual dependencies.
- [ ] `.gitignore` excludes local and sensitive files.
- [ ] `LICENSE` is present.

## Sensitive Files

Do not upload:

- [ ] `.env`
- [ ] `config.json`
- [ ] API Keys
- [ ] `logs/`
- [ ] `releases/`
- [ ] `last_essay_capture.png`
- [ ] `__pycache__/`
- [ ] `build/`
- [ ] `dist/`
- [ ] `*.spec`

## Smoke Test

- [ ] `python -m py_compile src/springpaper.py`
- [ ] App launches successfully.
- [ ] About dialog opens.
- [ ] Existing scoring workflow is not changed.
- [ ] Logs still write locally.

## First Commit

Recommended message:

```text
Initial release: SpringPaper v1.0.0
```
