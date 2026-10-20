---
title: The TCPR protocol
position: 2
---

TCPR is a simple TCP protocol. Messages between the TCPR client and server are plain text.

To auth, you have to send the RCON password in plain text (as defined by `sv_rconpassword`) terminated by a newline.
When the wrong password is entered, the connection is closed.

The TCPR server will determine the newline type depending on what you sent during auth.
For example, you can use the newline character `\n` as well as `\r\n` (CRLF) during auth. The setting will then be used for [the rest of the session](https://forum.thd.vg/threads/complete-tcpr-documentation.27028/#post-400427).
{: .info }

Messages are generally prefixed by the current time, in the `[HH:MM:SS] ` format.

The TCPR server will split lines [longer than ~16k bytes](https://forum.thd.vg/threads/build-1865-engine-update-sponges-in-tdm-windows-modded-server-fixes.25483/).  
This limit might be extended in the future, but [don't send that much data all at once](https://forum.thd.vg/threads/complete-tcpr-documentation.27028/#post-400427).
{: .error }

Because TCP is stream-based, your network library sometimes will return you a packet that does not contain an entire TCPR message or that contains more than one. To avoid this, you should read TCPR messages until your newline character.
{: .warning }

Commands works the same way as from the ingame console. You can send commands terminated by your newline. KAG built-in commands are prefixed by a slash `/` character. To send AngelScript code, omit the slash.
You may get a list of commands using `/help` or `/list`. `autoconfig` variables are exposed as commands and as global AngelScript variables.

`/rcon` is only required when using the ingame console.
{: .info }

The doublequote `"` character is broken in the ingame console, but works through TCPR.
{: .info }

Script `tcpr()` allows to send messages exclusively to TCPR clients, but not to logs.  
`sv_print_tcpr_specific` logs `tcpr()`-sent messages.  
`sv_tcpr_everything` hides non-TCPR messages from TCPR clients, in which case only messages sent by `tcpr()` and _some_ messages (such as the server shutting down) will be received by TCPR clients.
