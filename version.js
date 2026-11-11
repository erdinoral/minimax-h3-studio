const { execFileSync } = require("child_process")

module.exports = async (kernel) => {
  const gitPath = kernel.which("git") || "git"
  const git = (args) => {
    try {
      return execFileSync(gitPath, args, { cwd: __dirname, encoding: "utf8", timeout: 30000, stdio: ["ignore", "pipe", "ignore"] }).trim()
    } catch (e) {
      return null
    }
  }
  git(["fetch", "--tags", "--quiet", "origin"])
  // Only releases that ship this switcher are offered, so the menu can always switch back.
  const tags = (git(["tag", "--list", "v*", "--sort=-v:refname"]) || "").split("\n").filter(Boolean)
    .filter((tag) => git(["cat-file", "-e", `${tag}:version.js`]) !== null)
    .slice(0, 15)
  const current = git(["describe", "--tags", "--exact-match", "HEAD"])
  const detached = git(["symbolic-ref", "-q", "HEAD"]) === null
  return {
    run: [
      {
        method: "input",
        params: {
          title: "Switch version",
          description: "Pick an earlier release if something broke after an update, or go back to the latest. Your films, gallery and settings (studio/data) and downloaded models are kept. ComfyUI itself is not pinned and stays on its newest version.",
          form: [{
            type: "select",
            key: "version",
            title: "Version",
            default: detached && current ? current : "latest",
            items: [{ text: "Latest — keep following updates", value: "latest" }].concat(
              tags.map((tag) => ({ text: tag === current ? `${tag} (current)` : tag, value: tag }))
            )
          }]
        }
      },
      {
        method: "local.set",
        params: {
          version: "{{input.version}}"
        }
      },
      {
        method: "shell.run",
        params: {
          shell: "{{which('bash')}}",
          message: [
            "{{local.version === 'latest' ? '(git symbolic-ref -q HEAD >/dev/null || git checkout main) && git pull --ff-only' : 'git checkout --detach ' + local.version}}"
          ]
        }
      },
      // The chosen version's own sync.js pins its custom nodes and packages.
      {
        method: "script.start",
        params: {
          uri: "sync.js"
        }
      },
      {
        method: "notify",
        params: {
          html: "{{local.version === 'latest' ? 'H3 Studio is on the latest version.' : 'H3 Studio is on ' + local.version + '. Update returns to the latest version.'}}"
        }
      }
    ]
  }
}
