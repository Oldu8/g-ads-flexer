## Objective

You're working on google-ads-mcp project, it's a MCP(model context protocal) server that wraps the google ads api for LLM's interaction. You will use the tools to search, fetch web page contents to read the docs, and implement.

### about google ads api

google ads offers it's own client sdk as well as REST api. Client one has python sdk, built on top of protobuf schema. REST api does not have any existing openapi specs but referenec docs.
we decided to go with python sdk, since it's well maintained and does most of the heavy lifting, i.e. retries, pagination, etc.

## resources

here are some high level resources:

1. read the `./refs/googleads.llms.txt` for resources related to google ads api
2. use the `./refs/fastmcp.llms.txt` for full list of docs on how mcp server works.
3. use the cloudflare tools fetch urls via md/html, which is cleaner and easy to digest.
4. you have access to `google-ads-python` which contains source code for the python sdk, as well as all the types generated from protocol buffers.

## RULES

1. we use `uv` for pagkage management, see `pyproject.toml` for details & configs.
2. after changes run `uv run ruff format .`and `uv run pyright`
3. Our goal is to provide 1:1 mapping to ALL google ads services, and wrap them to MCP tools for LLMs to interact with. You can use files to help you track progress. use the API reference or the google-ads python codebase to read all the services available, and implement it. For each service, implement tests and make sure they pass. The implementation should be FULLY typed, using generated types from google ads v20 services.

## CURRENT TASK

Here is the current task you're working on. Prioritize this over everything else.

We're in the middle of creating MCP tools based on google ads api. We need to ensure 1:1 mapping and fully type safe. You will create a `TRACKER.md`, list down all the existing services in google-ads-python, and then audit the current progress and mark them. Start with everything as "not impl". Next, we will start one by one.

FOR each service, we will using the generated proto buf types, fully annotate the endpoints/operations, and create lightweight tools for MCP. Some existing implementations might exist, but theymight NOT be ideal, since we need to ensure the inputs & outputs are fully using generated types for consistency. After you implement each service, write tests to cover it. Next, move on to next service until we're done. NOTE, we only focus on google ads **V25** api (see below — this was V20 originally; V20 is now sunset), only implement services exist.

**2026-08-11 update — target API version changed from V20 to V25.** V20 was
sunset by Google on 2026-06-10 and now hard-fails every live call with
`UNSUPPORTED_VERSION`; this was discovered while validating real credentials
against the boo.ua account, not as a planned migration. `google-ads` dep was
bumped to `31.2.0` and all `v20` import paths / `version="v20"` calls in
`src/` and `tests/` were mechanically replaced with `v25`. Type/shape drift
between v20 and v25 was fixed only where it broke `pyright` or `pytest` (two
files: `audience_insights_service.py`, `campaign_service.py`) — the service
list in `TRACKER.md` itself has **not** been re-audited against what v25
actually offers. See the migration note at the top of `TRACKER.md` for full
detail before continuing service-by-service work — don't assume every
"✅ Implemented" entry is still accurate without spot-checking against the
current v25 protos.

in the `TRACKER.md`, note down the task you're working on and high level steps. so that other agents can pick it up from you easily w/ context.
