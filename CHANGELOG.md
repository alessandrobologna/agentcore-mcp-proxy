# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2025-10-06

### Added
- FastAgent demo in `demo/fast-agent/` showcasing MCP sampling capabilities
- Demo directory overview in `demo/README.md`
- Separate `demo/Makefile` for AgentCore deployment and testing
- CHANGELOG.md to track version history

### Changed
- **Breaking**: Reorganized demo structure - moved runtime implementations to `demo/agentcore/`
  - `demo/runtime_stateless/` → `demo/agentcore/runtime_stateless/`
  - `demo/runtime_stateful/` → `demo/agentcore/runtime_stateful/`
  - `demo/template.yaml` → `demo/agentcore/template.yaml`
  - `demo/samconfig.toml` → `demo/agentcore/samconfig.toml`
- Simplified root `Makefile` to Python package targets only (test, lint, format, quality)
- Updated all documentation to reflect new directory structure
- Enhanced repository layout section in main README

### Fixed
- Corrected all path references in documentation after restructuring

## [0.1.2] - 2025-01-05

### Changed
- Updated Python version requirement to 3.11+
- Added CI testing matrix for Python 3.11, 3.12, and 3.13

### Fixed
- Updated package classifiers to reflect supported Python versions

## [0.1.1] - 2025-01-04

### Changed
- Moved demo resources into `demo/` directory for better organization
- Updated Makefile and Dockerfile paths to use `demo/` prefix

## [0.1.0] - 2025-01-03

### Added
- Initial PyPI release
- MCP STDIO proxy with SigV4 authentication for AgentCore Runtime API
- HTTP-to-STDIO bridge for stateful MCP sessions
- Support for MCP sampling and elicitation
- Session modes: `session`, `identity`, and `request`
- Cross-account support via IAM role assumption using `aws-assume-role-lib`
- Handshake replay for container restart resilience
- Sample stateless and stateful AgentCore runtime implementations
- Smoke test utilities
- Comprehensive documentation and examples

[Unreleased]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alessandrobologna/agentcore-mcp-proxy/releases/tag/v0.1.0
