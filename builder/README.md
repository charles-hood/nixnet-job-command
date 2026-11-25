# Builder

`gen_custom_answers.py` is a small CLI over the same profile-driven engine
the app uses at `app/custom_answers.py`.

Proofs, company hooks and voice all live in `profile.json`. There is no
hard-coded resume in this repository. Copy `profile.example.json`, put
your own facts in, then:

```
python3 builder/gen_custom_answers.py --profile profile.json seed/example_seed.json /tmp/answers.json
```

The web app generates the same answers automatically when a job is added
or when you POST `/api/jobs/<ref>/custom-answers`.
