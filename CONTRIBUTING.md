# Contributing to Orbis-Search

Thank you for your interest in contributing to Orbis-Search! We welcome contributions from the community to help make this standalone search MCP even better.

## How to Contribute

### 1. Reporting Bugs
- Use the GitHub Issue Tracker to report bugs.
- Provide a clear description of the issue and steps to reproduce it.

### 2. Suggesting Enhancements
- Open a GitHub Issue to discuss potential enhancements before diving into code.

### 3. Pull Requests
- Fork the repository.
- Create a new branch for your feature or fix.
- Ensure your code follows the existing style and is well-documented.
- Include unit tests for any new functionality.
- Submit a pull request with a detailed description of your changes.

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/orbis-search.git
   cd orbis-search
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use `.\.venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```bash
   pip install -e ".[dev,local]"
   ```

4. **Run tests:**
   ```bash
   pytest
   ```

## Code of Conduct
Please be respectful and professional in all interactions within this project.

## License
By contributing, you agree that your contributions will be licensed under the MIT License.
