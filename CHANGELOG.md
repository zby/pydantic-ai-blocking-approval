# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2024-11-30

### Changed

- **BREAKING**: Renamed `require_approval` parameter to `pre_approved` in `ApprovalToolset`
  - Old: tools in list required approval, others skipped
  - New: tools in list skip approval, others require it (secure by default)
- **BREAKING**: Merged `present_for_approval()` into `needs_approval()`
  - `needs_approval()` now returns `bool | dict` instead of just `bool`
  - Return `False` to skip approval
  - Return `True` for approval with default presentation
  - Return `dict` for approval with custom presentation (description, payload, presentation)
- **BREAKING**: Removed `PresentableForApproval` protocol

### Added

- `ApprovalMemory.list_approvals()` - enumerate all cached session approvals
- `ApprovalMemory.__len__()` - get count of cached approvals
- `ShellToolset` example in tests demonstrating pattern-based approval
- Design documentation (`docs/notes/design_motivation.md`)
- User stories documentation (`docs/notes/cli_approval_user_stories.md`)
- GitHub Actions CI for Python 3.12, 3.13, 3.14
- `py.typed` marker for type checker support

## [0.1.0] - 2024-11-29

### Added

- Initial release
- `ApprovalToolset` - wrapper for PydanticAI toolsets with approval checking
- `ApprovalController` - mode-based controller (interactive/approve_all/strict)
- `ApprovalMemory` - session cache for "approve for session" functionality
- `ApprovalRequest`, `ApprovalDecision`, `ApprovalPresentation` types
- `@requires_approval` decorator
- `ApprovalConfigurable` protocol for custom approval logic
