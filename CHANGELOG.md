# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.5] - 2025-10-21

### Fixed
- Installation badge generator now correctly uses config's `name` field for MCP server identifier
- Corrected VS Code install URLs to use `agentcoreMcpProxy` as server name

### Changed
- Reorganized README structure: moved Overview before Quick Start for better context
- Enhanced Quick Start section with clarification about renaming server and handling multiple proxies
- Updated badge styles to flat-square for consistency

### Added
- Example configuration for multiple AgentCore runtime proxies in VS Code
- `.DS_Store` to `.gitignore`

## [0.1.4] - 2025-10-17

### Added
- VS Code one-click installation badges for Quick Start section
- `install/generate-buttons.py` script for creating installation badge markdown
  - Supports customizable shields.io styles, colors, and logos
  - Clipboard integration for easy copying
  - Properly separates MCP config inputs as URL parameter
- `install/vscode/mcp.json` configuration with input prompts for AgentCore Agent ARN and assume role ARN

### Changed
- Enhanced README with Quick Start section featuring install badges for VS Code and VS Code Insiders
- Updated badge generator to use config's `name` field for MCP server identifier (instead of display name)

### Fixed
- Installation URL now correctly uses `agentcoreMcpProxy` as the server name from config

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

[Unreleased]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/alessandrobologna/agentcore-mcp-proxy/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alessandrobologna/agentcore-mcp-proxy/releases/tag/v0.1.0
