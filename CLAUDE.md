# Claude AI Agent Guide

This file provides guidance for AI agents (like Claude Code, Cursor, Windsurf, etc.) working on the MyDiffuser project.

## Project Context

**⚠️ IMPORTANT: Read [AGENTS.md](./AGENTS.md) first!**

The `agents.md` file contains comprehensive project context including:
- Hardware configuration (AMD ROCm, gfx1151, GTT memory)
- Architecture (client/worker split, model management)
- Key models and their characteristics
- Known issues and workarounds
- API endpoints and file structure

Always reference `agents.md` when starting new work to understand the project's unique constraints and architecture.

## Working on This Project

### Before Making Changes

1. **Understand the context** - Read relevant sections of `agents.md`
2. **Check existing code** - Look for similar patterns in the codebase
3. **Consider ROCm constraints** - Not all PyTorch/diffusers features work on AMD
4. **Mind the architecture** - Respect the client/worker separation

### Code Quality Standards

#### Running Linters

**After making significant changes, always run:**

```bash
ruff check src/
```

#### Known Acceptable Warnings

The project has **41 acceptable linting warnings** that should be ignored:

**E501 (Line too long):**
- 7 lines are 1-20 chars over 100 limit
- These are complex type hints, long strings, or config lines
- Not worth the refactoring effort

**B008 (File() in defaults):**
- 3 instances in FastAPI endpoints
- Pattern: `image: UploadFile = File(...)`
- This is standard FastAPI practice and works correctly

**What to fix vs ignore:**
- ✅ **Fix:** Structural errors (E111, E117), undefined names (F821), bad exception handling (B904)
- ✅ **Fix:** Import sorting (I001), unused variables (F841)
- ⚠️ **Consider:** Lines >120 chars, whitespace issues (W293)
- ❌ **Ignore:** E501 under 120 chars, B008 (FastAPI File()), minor style issues

### Common Pitfalls for AI Agents

#### 1. Getting "Lost" in Large Files

**Symptom:** Duplicate code, code after return statements, wrong indentation

**Prevention:**
- Read the full method/function before editing
- Use Edit tool with sufficient context
- Verify no return statement exists before adding code

**Example of what NOT to do:**
```python
def my_function():
    result = calculate()
    return result  # ← First return

    # ❌ UNREACHABLE CODE BELOW (agent got lost)
    result = calculate()  # Duplicate
    return result  # Duplicate return
```

#### 2. Wrong File Paths

**Symptom:** Edits fail, paths in config don't match actual structure

**Prevention:**
- Use Glob/Find to verify paths exist
- Check `src/mydiffuser/client/` vs `src/mydiffuser/server/`
- Project uses `client/` not `server/`

#### 3. Breaking ROCm Compatibility

**Symptom:** Code works on CUDA but fails on AMD

**Prevention:**
- Check `agents.md` for known ROCm issues
- Don't use `torch.compile()` without testing
- Video VAE decode must run on CPU (gfx1151 issue)
- Avoid flash-attention or untested SDP backends

### Project-Specific Guidelines

#### Client/Worker Architecture

**Client (port 8000):**
- FastAPI server with web UI
- NO PyTorch/GPU dependencies
- Job submission and tracking
- Database operations (SQLite)

**Worker (port 8001+):**
- FastAPI inference server
- All GPU/model operations
- Lazy model loading
- Direct generation endpoints

**Never:**
- Import PyTorch in client code
- Do inference in client code
- Mix concerns between client/worker

#### Database Operations

The project uses SQLite with:
- `outputs/runs.db` - Main database
- `data/performance.db` - Performance tracking
- FTS5 full-text search on prompts

**When modifying schema:**
1. Update version number in `database.py`
2. Add migration logic
3. Test backfill operations
4. Update `agents.md` documentation

#### Model Management

**Loading strategy:**
- Eager: Both models loaded at startup (~60GB)
- Lazy: Models swap on demand (~30GB)
- Controlled via `MYDIFFUSER_LAZY` env var

**When adding new models:**
1. Update `config.py` with model ID
2. Add to `generators/` or `inference/`
3. Register in worker `app.py`
4. Update health endpoint to track it
5. Document in `agents.md`

### Testing Changes

```bash
# Lint check
ruff check src/

# Type check (optional, not strict)
mypy src/mydiffuser

# Run server (image only)
python scripts/run_server.py

# Run with video enabled
MYDIFFUSER_VIDEO=1 python scripts/run_server.py

# Lazy loading mode
MYDIFFUSER_LAZY=1 MYDIFFUSER_VIDEO=1 python scripts/run_server.py
```

### Documentation Updates

**When making significant changes, update:**
- `agents.md` - Architecture, features, known issues
- `README.md` - User-facing documentation
- This file (`CLAUDE.md`) - If you discover new patterns/issues

**Don't create:**
- New documentation files without explicit request
- Redundant guides that duplicate `agents.md`

## Common Tasks

### Adding a New Endpoint

1. Choose correct location:
   - Client: `src/mydiffuser/client/routes.py` or `*_routes.py`
   - Worker: `src/mydiffuser/worker/app.py`

2. Follow existing patterns:
   - Use type hints (Annotated[str, Form()])
   - Add docstrings with Args/Returns
   - Include error handling with `from e` or `from None`
   - Log important operations

3. Update health dashboard if needed

### Adding a New Model

1. Create generator class in `inference/` or `generators/`
2. Inherit from base class if applicable
3. Implement lazy loading pattern
4. Add unload capability
5. Update worker health endpoint
6. Test memory usage
7. Document in `agents.md`

### Fixing ROCm Issues

1. Check `vae-issues.md` and `agents.md` first
2. Test on actual hardware (Framework Desktop)
3. Consider CPU fallback for unstable operations
4. Document workaround in `agents.md`
5. Add configuration option if needed

## Git Workflow

**When committing:**
- Fix ruff errors first (except the 41 acceptable ones)
- Test basic functionality
- Write clear commit messages
- Follow existing style

**Commit message style:**
```
type: brief description

- Detailed point 1
- Detailed point 2

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Getting Help

- **Architecture questions**: See `AGENTS.md`
- **Quick start**: See `docs/QUICK_START.md`
- **Lambda deployment**: See `docs/LAMBDA_MANAGEMENT.md`
- **Client/Worker status**: See `docs/CLIENT_WORKER_STATUS.md`
- **GPU hang recovery**: See `docs/GPU_HANG_RECOVERY.md`

## Summary Checklist

Before finishing work:
- [ ] Read relevant sections of `agents.md`
- [ ] Run `ruff check src/` (41 warnings are OK)
- [ ] Test the change locally if possible
- [ ] Update `agents.md` if architecture changed
- [ ] No duplicate code or unreachable code
- [ ] Client/worker separation maintained
- [ ] Exception handling uses `from e` or `from None`
