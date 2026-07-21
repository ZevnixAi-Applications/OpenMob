# CI workflows (add these to .github/workflows/ via the GitHub web editor)

The GitHub token used from the CLI lacks the `workflow` scope, so these workflow files can't be pushed from here. Copy `release.yml` into `.github/workflows/` using GitHub's web editor (Add file → Create new file), which has no such restriction.
