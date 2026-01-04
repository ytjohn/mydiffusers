# Claude AI Agent Guide

**⚠️ IMPORTANT: Read [AGENTS.md](./AGENTS.md) for the comprehensive guide!**

This file previously contained working guidelines and development best practices for AI agents. All content has been consolidated into [AGENTS.md](./AGENTS.md) for easier maintenance.

## What's in AGENTS.md

The AGENTS.md file contains:

### Project Context
- Hardware configuration (AMD ROCm, gfx1151, GTT memory)
- Architecture (client/worker split, model management)
- Key models and their characteristics
- Known issues and workarounds
- API endpoints and file structure

### Development Guidelines
- Issue tracking with bd (beads)
- Code quality standards (linting, testing)
- ROCm/gfx1151 specific considerations
- Client/worker architecture details
- Model management and loading strategies

### AI Agent Guidelines
- Common pitfalls to avoid (getting lost in files, wrong paths, ROCm compatibility)
- Git workflow and commit message format
- Summary checklist before finishing work
- Testing and documentation practices

## Quick Reference

```bash
# Check for ready work
bd ready --json

# Lint check
ruff check src/

# View project structure
ls -la src/mydiffuser/
```

**Always reference [AGENTS.md](./AGENTS.md) when starting new work to understand the project's unique constraints and architecture.**
