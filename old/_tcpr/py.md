---
title: Using TCPR with Python 3
position: 3
---

In order to use TCP sockets in Python, you will need to import the `socket` library.  
This script will read chat and console logs from TCPR. It will print to the logs whenever a chat message is detected, and if the chat message is '!help', it will broadcast a message.
The first argument passed to the script will be the ip address and the second argument will be the port to connect to, and read the password from the standard input.

~~~ python
#!/usr/bin/python

import socket
import sys
import re # Regular expression

# Read from the socket until the newline character.
# Unfortunately python sockets doesn't have a simple feature for that.
def readUntilNewline(sock, rest):
	# Get the rest data from the last read, splitted over '\n'.
	# So if there is more than one element in rest, we have a line ready.
	if len(rest) >= 2:
		# Tuple, first element is the requested line, second is the rest
		return (rest[0], rest[1:])

	# ... in the other case use it as the beginning of the line to read
	chunkList = rest

	# Read chunks of data
	while True:
		# Receive a data chunk
		data = sock.recv(1024).decode()

		if not data:
			raise EOFError("Socket closed")

		chunkList.append(data)
		tokenized = data.split("\n")

		# We found a '\n' character: return the user the line he wants and the rest data
		if "\n" in data:
			# Get every chunk but the last one and add the first part of the latest chunk manually.
			return ("".join(chunkList[:-1]) + tokenized[0], tokenized[1:])

# Beginning of the script
if len(sys.argv) <= 2:
	print("Usage: tcpr.py [server] [port]")
	sys.exit()

sock = socket.socket()

try:
	sock.connect((sys.argv[1], int(sys.argv[2])))
except ConnectionError:
	print("[TCPR] Connection error")
	sys.exit()

pwd = input("[TCPR] Enter password: ")
sock.send((pwd + "\n").encode())

sock.send("/msg Hello from Python!\n".encode())

rest = []
try:
	while True:
		line, rest = readUntilNewline(sock, rest)

		# Regular expression search: look up for the chat messages exclusively
		chatResult = re.search("\[\d{2}:\d{2}:\d{2}\] \<(.*)\> (.*)", line)

		# If the message is really a chat message
		if chatResult is not None:
			chatSender = chatResult.group(1)
			chatMessage = chatResult.group(2)

			print("[App] Received chat message from '", chatSender, "': '", chatMessage, "'", sep="")

			if chatMessage == "!help":
				sock.send(("/msg Hi, " + chatSender + ", welcome to this server! Some useful info: ...\n").encode())

		print("[Server]", line)
# Connection lost to the server
except EOFError:
	print("[TCPR] Connection lost.")
~~~

Example usage: `python tcpr.py localhost 50301`

You should receive player messages along with other servers logs, including TCPR feedback:

	[App] Received chat message from 'FIST! Asu': '!hello'
	[Server] [15:28:09] <FIST! Asu> !hello
	[Server] [15:28:10] Config file not found 'help'
	[Server] [15:28:10] Loading blob config from help...
	[Server] [15:28:10] ERROR: Blob config not found... help
	[App] Received chat message from 'FIST! Asu': '!help'
	[Server] [15:28:10] <FIST! Asu> !help
	[Server] [15:28:10] RCON command from 127.0.0.1:17576 :
	[Server] [15:28:10] /msg Hi, FIST! Asu, welcome to this server! Some useful info: ...
	[Server] [15:28:10]
