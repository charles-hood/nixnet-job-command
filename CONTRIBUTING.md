# Contributing to NixNet Job Command

Thanks for showing up. This project is a local-first scaffold. Keep it that way.

## Ground rules

- Python 3.9+, standard library only in the app. No pip dependency for `make run`.
- Do not add telemetry, accounts, or a hosted backend.
- The server binds `127.0.0.1` by default and refuses `0.0.0.0` unless `NJC_ALLOW_PUBLIC_BIND=1`.
- Never commit `data/`, `*.db`, `.env`, `config.toml`, `profile.json`, or anything that looks like a real job search.
- Treat `profile.example.json` and `seed/example_seed.json` as fiction. If you add examples, use clearly fake companies (Acme Cloud, Globex AI) and `example.com` contacts.
- The nixfred hexagon and wordmark in `brand/` are locked. Do not recolor, restyle, or redraw them. See [the nixfred brand standard](https://github.com/nixfred/nixfredOS/blob/main/brand/README.md).

## How to work

```
./setup.sh
make test
make run
```

The app lives in `app/`. Profile-driven custom answers live in `app/custom_answers.py`. Config is loaded by `app/config.py`.

Open a pull request with a clear description, a passing `make test`, and no secrets in the diff. If you change the API or the seed schema, add a note to `CHANGELOG.md`.
