# GitHub Setup for TFI-banisa

## Quick Start

### 1. Create Repository on GitHub

1. Go to https://github.com/new
2. Repository name: **tfi-banisa**
3. Description: "Telugu movie meme/sticker store with semantic search"
4. Visibility: **Public** (or Private if you prefer)
5. Initialize: **Do NOT** check "Add a README" (we already have one)
6. Click **Create repository**

### 2. Push to GitHub

Replace `YOUR_USERNAME` with your GitHub username:

```bash
cd ~/Projects/TFI-banisa

# Add remote
git remote add origin https://github.com/YOUR_USERNAME/tfi-banisa.git

# Rename branch if needed (GitHub defaults to 'main')
git branch -M main

# Push
git push -u origin main
```

### 3. Verify

Visit `https://github.com/YOUR_USERNAME/tfi-banisa` in your browser. You should see:
- ✅ CLAUDE.md, AGENTS.md, GEMINI.md
- ✅ tasks.md (comprehensive task list)
- ✅ Initial commit with 4 files

## After Initial Push

### Add GitHub Secrets (Optional, for CI/CD later)

When you add automated testing or deployment, add:
- `HUGGINGFACE_TOKEN` (for model downloads, if needed)
- `OPENAI_API_KEY` (for fallback, post-MVP)

**For now:** Not needed; all models are open-source.

### Create GitHub Issues (One Per Task)

You can auto-generate issues from `tasks.md`:

1. **Manually:** Copy each Phase into GitHub Issues, assign to yourself
2. **Script:** (Future) Write a script to parse `tasks.md` and create issues via GitHub API

Example issue title: **Phase 1.1.1: Environment & Dependencies Setup**
Example issue body:
```
- [ ] Create `.env.example` with all required variables
- [ ] Create `requirements.txt` with all Python dependencies
- [ ] Create `setup.sh` script
- [ ] Test script on Mac Mini

**Acceptance criteria:**
- `./setup.sh` runs without error
- All required models downloaded and cached
```

### Create Project Board (Optional)

1. Go to repo → **Projects** tab
2. Create **Project**: "TFI-banisa Implementation"
3. Add columns: **To Do**, **In Progress**, **Done**
4. Add cards from Issues (or manually track Phases)

## Branching Strategy (Post-MVP)

For future contributors or when you start Phases:

```bash
# Start Phase 2 (Core API)
git checkout -b feature/phase-2-core-api

# Commit changes
git add .
git commit -m "Implement Phase 2: Core API endpoints

- POST /api/memes/upload
- POST /api/memes/search
- GET /api/memes/{id}
- POST /api/memes/{id}/edit
"

# Push feature branch
git push origin feature/phase-2-core-api

# Open Pull Request on GitHub
# Request review, merge to main
```

## Documentation URLs (Once Pushed)

- **Repository:** https://github.com/YOUR_USERNAME/tfi-banisa
- **Issues:** https://github.com/YOUR_USERNAME/tfi-banisa/issues
- **Project Board:** https://github.com/YOUR_USERNAME/tfi-banisa/projects
- **README (once written):** https://github.com/YOUR_USERNAME/tfi-banisa#readme

## Next Steps

1. **Phase 1 (This Week):**
   - [ ] Create GitHub repo + push
   - [ ] Create GitHub Issues for Phase 1 tasks
   - [ ] Begin setup.sh (model downloads, Docker config)

2. **Phase 2 (Week 2):**
   - [ ] Create new branch `feature/phase-2-core-api`
   - [ ] Implement FastAPI endpoints
   - [ ] Merge PR to main

3. **Phases 3–5:** Follow same branch → PR → merge pattern

---

**Repo created locally:** `/Users/dark_mamba/Projects/TFI-banisa`
**Status:** Ready to push to GitHub
**Commit hash:** (output from git commit above)
