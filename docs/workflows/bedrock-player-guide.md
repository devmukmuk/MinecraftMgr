# Playing Game Night from Bedrock (Windows, Switch, phone, Xbox)

This guide is for players. Admins setting it up should read
[bedrock-crossplay.md](bedrock-crossplay.md).

You can join the same worlds as the Java players from the **Bedrock**
version of Minecraft. That's the version on Windows (from the Microsoft Store
or the Xbox app), Nintendo Switch, Xbox, PlayStation, iPhone/iPad and Android.

## Before your first visit

1. **Sign in to your Microsoft account in Minecraft.** The server knows you by
   your Xbox gamertag. No Java account is needed.
2. **Try to join once** (steps below). You'll probably see *"You are not
   whitelisted on this server!"*. That's expected: it lets the admin see your
   gamertag so they can add you.
3. **Tell the admin.** Once you're added, join again.

In the game your name shows with a dot in front, e.g. **`.YourGamertag`**.
That's how Bedrock players are told apart from Java players.

## Windows, phone or tablet: add the server

1. Open Minecraft and go to **Play → Servers**.
2. Scroll to the bottom and choose **Add Server**:
   - **Server Name:** `Game Night`
   - **Server Address:** `192.168.1.113` when you're at home, or
     `gamenightbymike.com` from anywhere else
   - **Port:** `19132`
3. Save it, then select it to join.

## Nintendo Switch (at home)

The Switch can't type in a server address, but at home the server shows up
like a game on your local network:

1. Make sure the Switch is on the **home Wi-Fi**.
2. Open Minecraft and go to **Play → Friends**.
3. Under **LAN Games**, pick **Game Night by Mike**.

If it isn't listed, tell the admin. Switch play away from home needs extra
setup that isn't done yet.

## Getting to the right world

Everyone arrives in the **lobby world (Gravestone)** first. To go to another
world, type in chat:

```
/server blue
```

Replace `blue` with whichever world you're playing in.

## If something goes wrong

| You see | What to do |
|---|---|
| "Unable to connect to world" / it can't find the server | Check the address and port `19132`. At home, use `192.168.1.113`. |
| "You are not whitelisted on this server!" | Tell the admin your gamertag. They need to add you to that world. |
| The server was there, then everyone got kicked | The server may be restarting or doing its weekly backup (Sunday around 3 am). Try again in a few minutes. |
