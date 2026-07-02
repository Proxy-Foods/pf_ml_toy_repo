# Contributing workflow

This repo is a sandbox for practicing a standard ticket-driven dev workflow. Suggested convention:

## 1. Branch naming (from a Jira ticket)

```
<type>/<JIRA-KEY>-<short-description>
```

Example:
- `SCRM-7550-Development-Lifecycle-Branch-Commit-Push-Review`


```bash
git checkout main
git pull origin main
git checkout -b SCRM-7550-Development-Lifecycle-Branch-Commit-Push-Review
```

⚠️ All commits made after this point land on `SCRM-7550-Development-Lifecycle-Branch-Commit-Push-Review`, not
`main` — `main` isn't touched until the PR is merged. Before committing, it's worth
double-checking you're on the right branch:

```bash
git branch --show-current
```

## 2. Make a change

Keep changes small and scoped to one ticket, e.g.:
- Add/edit a JSON file under `data/`
- Adjust `build_prompt` or `sample_ingredients` in `notebooks/recipe_generator.ipynb`
- Add a test

## 3. Commit

Reference the Jira key in the commit message so it links automatically if Jira/GitHub are integrated:

```bash
git add .
git commit -m "TOY-12: add desserts.json ingredient category"
```

## 4. Push

```bash
git push -u origin SCRM-7550-Development-Lifecycle-Branch-Commit-Push-Review
```

## 5. Open a pull request

```bash
gh pr create --fill --base main
```
(or open the PR from the GitHub UI — link the Jira ticket in the description)

## Notes for reviewers

- Never commit a real `.env` file — only `.env.example` should be tracked.
- `data/*.json` files must include a top-level `category` and an `items` array to be picked up by the notebook.
