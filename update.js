module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        shell: "{{which('bash')}}",
        message: [
          // A version chosen in Switch version is a detached checkout; Update returns to the latest.
          "git symbolic-ref -q HEAD >/dev/null || git checkout main",
          "git pull"
        ]
      }
    },
    // Loaded after the pull, so the backend matches the code that just arrived.
    {
      method: "script.start",
      params: {
        uri: "sync.js"
      }
    }
  ]
}
