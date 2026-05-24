/**
 * Commit message format for mineru-runpod.
 *
 * Enforces the Conventional Commits spec so semantic-release can derive
 * version bumps + changelog entries automatically.
 *
 *   type(scope): subject
 *
 *   <body>
 *
 *   BREAKING CHANGE: <description>
 *
 * Allowed types match the matrix in .releaserc.json — keep the two in sync
 * or semantic-release will see commits it doesn't know how to classify.
 */
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'feat',     // new feature → minor bump
        'fix',      // bug fix → patch bump
        'perf',     // performance → patch bump
        'refactor', // no behaviour change → patch bump
        'docs',     // docs only → no release (unless scope is 'readme')
        'test',     // tests only → no release
        'build',    // build / Docker / deps → no release
        'ci',       // CI workflows → no release
        'chore',    // anything else → no release
        'revert',   // → patch bump
        'style',    // formatting → no release
      ],
    ],
    // Slightly relaxed line lengths — error messages can be long.
    'body-max-line-length': [1, 'always', 120],
    'footer-max-line-length': [1, 'always', 120],
  },
};
