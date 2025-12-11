# Blocking Approval: Context and Motivation

## LLM Clients vs Agent Frameworks

| Layer | Examples | Responsibility |
|-------|----------|----------------|
| **LLM Client** | `mistralai`, `openai`, `anthropic` SDKs | Stateless API calls |
| **Agent Framework** | PydanticAI, Mistral Vibe, LangChain | Tool orchestration, agent loops |

LLM client libraries are stateless - the user manages the tool execution loop. Agent frameworks manage the loop internally, which affects where approval decisions can be made.

## How Other Agent Frameworks Handle Approval

| Agent Framework | Blocking Approval |
|-----------------|-------------------|
| Mistral Vibe | Built-in (ALWAYS/ASK/NEVER) |
| Claude Code | Built-in |
| LangChain | Built-in (`HumanApprovalCallbackHandler`) |
| PydanticAI | Deferred (via `ModelRequest` events) |

## Deferred vs Blocking Patterns

PydanticAI's current approval model is **deferred** - tool calls are collected, execution pauses, and a new run continues after approval. This works well for batch/review workflows.

For interactive scenarios (CLI agents, multi-step dangerous operations), blocking approval provides a different UX where the agent can see results before planning the next step. Both patterns have their place depending on the use case.

Stateless functions are good - they're easier to test, reason about, and compose. But some things are inherently stateful. Blocking approval is one of them: the system must pause execution and wait for user decision - that's a "waiting for approval" state. Additionally, session caching requires remembering past decisions. This library provides the minimum state needed: execution suspension and a session-scoped approval cache.

## This Library's Approach

- Sync and async callback support
- Session caching ("approve for session")
- Protocol-based extensibility (`SupportsNeedsApproval`)
- Three approval states: blocked, pre_approved, needs_approval
- Mode-based controller: interactive, approve_all, strict

## References

- [Mistral Vibe](https://github.com/mistralai/mistral-vibe)
- [LangChain Human Approval](https://python.langchain.com/docs/modules/agents/tools/human_approval)
- [HumanLayer](https://humanlayer.dev/)
