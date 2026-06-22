"""hippocampus -- centralised conversation context / memory module.

Phase 1 scope: a self-contained module living inside the AI Core process
that owns its *own* chat-history persistence (a dedicated SQLite access
layer + engine over the shared ``db/tendou_arisu.db``) and a
:class:`~hippocampus.context.manager.ContextManager` that channels reach
over HTTP today and that AI Core can import in-process later.

This module deliberately does NOT touch any channel (QQ bot etc.) code.
"""
