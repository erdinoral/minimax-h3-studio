// Menu switch for "Auto-update on Start"; pinokio.js passes the new state as args.enable.
module.exports = {
  run: [
    {
      when: "{{args.enable}}",
      method: "fs.write",
      params: {
        path: ".auto-update",
        text: "Start pulls launcher updates while this file exists.\n"
      }
    },
    {
      when: "{{!args.enable}}",
      method: "fs.rm",
      params: {
        path: ".auto-update"
      }
    }
  ]
}
