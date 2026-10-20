---
title: TCPR - Getting Started
position: 1
---

TCPR is the standard way to administrate a KAG server remotely through TCP. Its usage is similar to that of RCON, accessed from the `/rcon` command in KAG's built-in console (home key).  
Because of its nature, it's easy to use in nearly every language. This documentation will provide an example application in Python, but it is doable (with external libraries) in C++, Java, C#...

You can find an [(outdated) documentation of TCPR](https://wiki.kag2d.com/wiki/Remote_Administration) on the KAG Wiki.  
KAG build [`1591`](https://forum.thd.vg/threads/kag-build-1591-maps-and-bombs.24220)(?) came up with overhauled TCPR with more capabilities (such as now being Windows-compatible) and build [`1865`](https://forum.thd.vg/threads/build-1865-engine-update-sponges-in-tdm-windows-modded-server-fixes.25483) came up with a TCPR maximal line size change.
{: .info }

`sv_tcpr` has to be set to `1` for TCPR to be enabled. Then, set `sv_rconpassword` to the password of your choice (which can be used both to login with TCPR and over RCON).
The `50301` port has to be forwarded for TCP (whereas the game itself uses UDP over `50301` as well) to connect from another machine.
