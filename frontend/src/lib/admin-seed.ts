/** Starter docs for the vault admin section (`<dir>/` + path below). All markdown. */

export interface StarterDoc {
	/** Path under the admin dir, e.g. `templates/meeting.md`. */
	path: string;
	content: string;
	/** Page-type slug wired into `admin.templates` on seed (when absent). */
	template?: string;
	/** Prompt name wired into `admin.prompts` on seed (when absent). */
	prompt?: string;
}

export const LAYOUT_DOC = 'templates/layout';

export const STARTER_DOCS: StarterDoc[] = [
	{
		path: 'index',
		content: `# Vault administration

This section holds the docs the librarian manages the vault by.

- \`templates/\` — page-type templates. New pages of a known type start from their template.
- \`templates/layout.md\` — the wiki layout every page follows.
- \`prompts/\` — reusable prompts the librarian reads before a run.
`
	},
	{
		path: LAYOUT_DOC,
		content: `# Layout

New pages follow this shape:

- \`# Title\` — the page name as heading.
- A short intro paragraph.
- \`##\` sections, one per topic.
- \`tags:\` frontmatter when the page belongs to a type (see templates).
`
	},
	{
		path: 'templates/meeting',
		content: `---
tags: [type/meeting]
---

# Meeting — <title>

- Date:
- Attendees:

## Notes

## Decisions

## Actions
`,
		template: 'meeting'
	},
	{
		path: 'templates/project',
		content: `---
tags: [type/project]
---

# Project — <title>

- Status:
- Owner:

## Goal

## Notes
`,
		template: 'project'
	},
	{
		path: 'templates/person',
		content: `---
tags: [type/person]
---

# <name>

- Role:
- Contact:

## Notes
`,
		template: 'person'
	},
	{
		path: 'prompts/capture-triage',
		content: `# Capture triage

Look at the pending capture queue. Group requests into actionable items,
apply the ones the vault instructions allow, and review every entry —
applied, approved or rejected. Never leave a request pending silently.
`,
		prompt: 'capture-triage'
	},
	{
		path: 'prompts/vault-sweep',
		content: `# Vault sweep

Walk every note. Fix titles, fold duplicates, link related pages, and queue
updates for anything stale. Follow the layout template for new pages.
`,
		prompt: 'vault-sweep'
	}
];
