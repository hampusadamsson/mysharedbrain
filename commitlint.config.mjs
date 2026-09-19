// Conventional Commits rules, inlined so the repo needs no extra dependency
// for linting. Kept in sync with the release-please changelog sections and the
// convention documented in AGENTS.md.
export default {
	rules: {
		'type-enum': [
			2,
			'always',
			[
				'feat',
				'fix',
				'perf',
				'revert',
				'docs',
				'refactor',
				'test',
				'build',
				'ci',
				'chore'
			]
		],
		'type-case': [2, 'always', 'lower-case'],
		'type-empty': [2, 'never'],
		'scope-case': [2, 'always', 'lower-case'],
		'subject-empty': [2, 'never'],
		'subject-full-stop': [2, 'never', '.'],
		'header-max-length': [2, 'always', 100],
		'body-leading-blank': [2, 'always'],
		'footer-leading-blank': [2, 'always']
	}
};
