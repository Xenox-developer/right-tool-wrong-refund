An AI assistant can call the approved refund tool and still issue an unauthorized refund.

I built a local test around that problem: 8 synthetic customer documents with misleading refund claims, plus 4 benign controls. Qwen2.5 7B and Qwen3 8B each processed every document twice, for 48 measured generations.

Each proposed tool call was replayed against two fresh SQLite ledgers. Both servers checked the tool name, argument schema, currency and duplicate requests. The second also checked customer identity, the requested order and the remaining refund allowed by merchant policy.

Unauthorized writes on the attack inputs:
• Qwen2.5: 12/16 with the tool allowlist, 0/16 with business-rule checks.
• Qwen3: 10/16 with the tool allowlist, 0/16 with business-rule checks.

Both servers completed all 8/8 benign trials per model. All 48 responses contained a native tool call; there were no protocol or connection errors.

One Qwen3 proposal requested $109 where the trusted policy allowed $100. Another selected a different order belonging to the same customer. Both passed the baseline and were blocked by the policy server.

Blocking a bad call left the customer's task unfinished. On attacked inputs, exact refund completion stayed at 2/16 for Qwen2.5 and 6/16 for Qwen3 under both server policies.

This is a small synthetic pilot with local database writes and no real payments. The two seeds agreed within each case. There were no paired clean versions of the attack documents, so these counts cannot isolate the effect of the misleading text. No paid API calls were used.

Code, fixtures, raw responses, SQLite ledgers and results:
https://github.com/Xenox-developer/right-tool-wrong-refund

Research inspiration: Beyond Instruction Override. This is an independent adaptation:
https://arxiv.org/abs/2611.07640

#AISecurity #PromptInjection #AIEngineering
