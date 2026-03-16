# Contributing to Senten

Thank you for your interest in contributing to Senten!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/TheBigS1981/Senten.git
cd Senten

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
npm install

# Build CSS
npm run build:css

# Run the app
uvicorn app.main:app --reload
```

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=term-missing

# Single test file
pytest tests/test_translate.py -v
```

## Code Style

- **Python**: Follows PEP 8, enforced by ruff
- **JavaScript**: Vanilla JS, no frameworks
- **CSS**: Tailwind CSS v3
- **Commits**: We use [Conventional Commits](https://www.conventioncommits.org/)

### Commit Message Format

```
<type>(<scope>): <description>

Examples:
feat(auth): add OAuth2 login with GitHub
fix(cart): prevent duplicate items on rapid clicks
chore(deps): update express from 4.18 to 4.19
refactor(orders): extract order validation into service
```

### Type Prefixes

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `chore` | Build/tooling changes |
| `refactor` | Code restructuring |
| `test` | Adding tests |
| `docs` | Documentation only |
| `style` | Formatting only |
| `perf` | Performance improvement |
| `ci` | CI/CD changes |

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Ensure all tests pass (`pytest`)
5. Run linting (`npm run lint`)
6. Commit your changes following the commit format
7. Push to your fork and open a Pull Request

## Pull Request Checklist

- [ ] Tests pass (`pytest`)
- [ ] Lint passes (`npm run lint`)
- [ ] New code has tests
- [ ] Documentation updated if needed
- [ ] Commit message follows Conventional Commits

## Getting Help

- Open an issue for bugs or feature requests
- For security issues, see SECURITY.md
