# GitHub Push Checklist

Use this checklist before pushing deployment-related changes.

## 1) Confirm Scope

- Backend code changed?
- Agent code changed?
- Frontend code changed?
- Docs changed?

## 2) Validate Locally

```bash
cd backend && pytest tests/ || true
cd ../frontend && npm run build
```

## 3) Verify Deployment Scripts

```bash
bash -n scripts/gcp/deploy.sh
bash -n scripts/gcp/deploy-agent.sh
```

## 4) Review Git Diff

```bash
git status
git diff -- README.md docs/GCP_DEPLOYMENT.md docs/DEPLOYMENT.md scripts/gcp/deploy.sh scripts/gcp/deploy-agent.sh
```

## 5) Commit

```bash
git add README.md docs/GCP_DEPLOYMENT.md docs/DEPLOYMENT.md docs/GITHUB_PUSH_CHECKLIST.md scripts/gcp/deploy-agent.sh
git commit -m "docs: align architecture and GCP deployment with separated agent service"
```

## 6) Push

```bash
git push origin <your-branch>
```

## 7) Pull Request Checklist

- PR description includes architecture update (frontend/backend/agent split)
- Secret Manager policy explicitly documented
- Deployment commands tested
- Any behavior changes called out

## Inputs Usually Needed

- target branch (`main`, `develop`, etc.)
- commit message preference
- whether to squash commits
- whether to open PR immediately after push

