"""The line's suite runs as on a machine with no git identity (the owner's file 006, 22 November 2026: GitHub's runner
has none, and a test that committed without the test world's environment failed there while passing on the Mac). Every
run, here and on GitHub alike: no global or system git configuration, and git never guesses an identity, so a commit
run outside the world's own identity fails everywhere, not only on GitHub."""
import os

os.environ.update({"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "1",
                   "GIT_CONFIG_KEY_0": "user.useConfigOnly", "GIT_CONFIG_VALUE_0": "true"})
for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
    os.environ.pop(k, None)
