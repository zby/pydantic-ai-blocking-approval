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

Stateless functions are good - they're easier to test, reason about, and compose. But some things are inherently stateful. Approval is one of them: you need to remember what was approved during a session to avoid repetitive prompts for the same operation. This library provides the minimum state needed to cover this case - just a session-scoped cache of approval decisions.

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
