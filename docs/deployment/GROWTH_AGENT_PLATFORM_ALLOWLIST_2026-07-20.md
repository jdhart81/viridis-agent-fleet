# Growth-agent platform policy allowlist — 2026-07-20

**Purpose:** FA-B4 policy gate for autonomous outbound. This is a machine-enforced allowlist, not a pre-send content review.
**Default:** a platform/target is disabled unless both the platform policy and target-specific permission are documented.
**Last reviewed:** 2026-07-20.

## Allowlist

| Platform / target class | Platform-policy result | Live-post status | Conditions |
|---|---|---|---|
| Smithery listings owned by `hartjustin6`, including `agent-market-network` | **Allowed.** Smithery documents an owner-authenticated `PATCH /servers/{qualifiedName}` API specifically for updating display metadata including description and homepage. | Cleared for autonomous metadata refresh | Dedicated Smithery API key; adapter hard-restricts the namespace to `hartjustin6/*` and the homepage to an owned Viridis discovery surface; 30-day per-listing cooldown; no creation or modification of another owner's listing. |
| Discord bot API, server/channel that has explicitly installed and authorized the Viridis bot | **Conditionally allowed.** Discord provides bot accounts for automation. Self-bots/user-account automation are forbidden; unsolicited bulk messages and spam are forbidden. | Disabled until the specific server/channel authorizes the bot | Bot token only; never a user token. Channel-level allowlist, 14-day cooldown, one accurate message, no DMs, no bulk send. |
| CDP Discord `#x402` | The platform can support a bot, but the audited Viridis user membership does not grant authority to install or automate a bot in CDP's server. The successful 2026-07-20 post was a user-authorized one-time post, not bot permission. | **Not cleared for autonomous posting** | Ask CDP server staff to install/authorize the Viridis bot or skip the target. Never automate Justin's Discord user account. |
| `jdhart81/viridis-agent-fleet` owned documentation | **Allowed.** GitHub permits API automation and project-related promotional text in an owner's repository, subject to rate/abuse limits. The official Contents API supports a repository-scoped write token. | Cleared for autonomous refresh of `docs/LIVE_AGENT_SUITE.md` only | Fine-grained token with Contents write on this repository; adapter hard-restricts repository, path, branch, and API; 14-day cooldown; no issues, PRs, stars, follows, notifications, or third-party writes. |
| Third-party GitHub issues, discussions, and pull requests used primarily as promotion | GitHub prohibits bulk promotion, unsolicited advertising, and advertising in other users' accounts, including monetized or excessive issue content. | **Not cleared by default** | A specific maintainer invitation or contribution policy that accepts project listings is required. One contribution per material listing change; cooldown alone does not make unsolicited promotion acceptable. |
| Curated ecosystem/awesome lists | Potentially acceptable as a genuine, policy-conforming listing contribution; target policy is repository-specific. | Disabled until each repository's contribution rules are recorded | No recurring “re-post” PRs. Update an existing listing only when the product facts materially change. |
| Public ESG/carbon agent directories | No common platform policy exists; each directory has separate submission/automation terms. | Not cleared | Add only after the exact directory's official submission/automation policy is reviewed and recorded. |
| Email/DM outreach | Anti-spam, privacy, and platform rules vary; the Wave-10 prompt does not provide a consent basis or cleared list. | Not cleared | No cold automated email or DM in v1. |

## Primary policy sources

- [Smithery — Update a server](https://smithery.ai/docs/api-reference/servers/update-a-server): official authenticated API for updating an owned server's description, homepage, and visibility metadata.
- [Smithery — Publish](https://smithery.ai/docs/build/publish): official distribution workflow for public Streamable HTTP MCP servers.
- [Discord — Automated User Accounts (Self-Bots)](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots): automation must use a bot account; normal-user automation is forbidden.
- [Discord Community Guidelines](https://discord.com/guidelines): no unsolicited bulk messages/spam, self-bots, or inauthentic engagement.
- [Discord — Bots & Companion Apps](https://docs.discord.com/developers/platform/bots): bot accounts can send messages through the official API when installed/authorized.
- [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service): human-created machine accounts and APIs are permitted, subject to API abuse/rate limits.
- [GitHub Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies): no automated excessive bulk promotion, unsolicited advertising, or advertising in other users' accounts; project-related promotion in one's own repository is permitted.
- [GitHub Contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents): owner-authenticated create/update for a repository file; fine-grained tokens can be limited to Contents write.

## Design-direction exception raised by FA-B4

The CDP x402 channel has demonstrated conversion, but Discord forbids automating Justin's user account and Viridis cannot independently install a bot in someone else's server. The standing options are:

1. request CDP staff to authorize/install the Viridis bot, after which the channel can be enabled with the cooldown; or
2. skip autonomous CDP posting and keep only policy-cleared first-party GitHub updates until another external target grants bot/API permission.

The growth agent must refuse to send when a target is not explicitly cleared. `GROWTH_AGENT_ENABLED=1` does not override this allowlist.
