# Platform compatibility evidence

The public endpoint currently advertises five tools. The diagnostic skill uses
only describe_agent and get_security_receipt. Host permission controls must
restrict the three assessment tools; skill text alone is not authorization.

Native Codex/Claude Code discovery and read-only diagnostic probes were completed
for earlier 0.1.2 packaging. Version 0.1.3 removes credential-reading examples and
adds existing public icon/privacy metadata. It makes no authenticated host test
or directory approval claim. The local OAuth candidate passes 31 synthetic tests
and the unchanged gateway affected suites pass 213 tests in its separate SDK.
No live provider consent, paid assessment or model-driven host turn was tested.

OpenAI has an unpublished draft in Viridis / Default project, with verified
individual publisher JUSTIN DANIEL HART and incomplete MCP configuration.
Claude source validation of public main 172b92a found four credential-reading
policy holds and missing icon/privacy metadata. This revision prepares fixes;
portal revalidation is required against its actual published source.

Hosted assessments use OAuth only once activated. Do not collect credentials
through conversations, skill inputs or user_config. No static-header or local
credential examples are distributed. Entitlement eligibility and exact host
callbacks remain platform review/setup gates. No checkout is bundled.
