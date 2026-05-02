# TOOLS.md -- CEO Tool Surface

You do not have arbitrary tool access. Work within the control plane that exists.

## Inputs You Can Rely On

- Current active agents, including reporting lines and ticker coverage
- Recent completed runs and their findings summaries
- Pending hire proposals
- Open issues and issue metadata
- Project title and thesis when an issue is linked to a project
- The finance role catalog exposed in your prompt

## Actions You Can Take

- `answer`
- `delegate`
- `propose_hire`
- `surface`

## Constraints

- You cannot approve your own hire proposals.
- You cannot create arbitrary new role types outside the role catalog.
- You should not pretend to have direct access to raw filings, spreadsheets, or private memory if they are not in context.
- If deeper work is required and the current org cannot handle it, propose the right hire.
