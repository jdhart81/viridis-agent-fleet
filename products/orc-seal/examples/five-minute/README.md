# Five-minute path: seal a result, then verify it

A tiny MCP server (`sample_server.py`, one tool, standard library only) wrapped by
`orc-seal`, and a short client (`drive.py`) that calls it and saves the receipt.

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install orc-seal
python drive.py did:web:yourdomain.com     # use your own domain
orc-seal verify receipt.json               # -> INTACT
```

That receipt proves the result was not altered after sealing. Nothing left your machine.

## Registered receipts (ISSUED)

With a registry key, the same run records the seal in the public registry, so a
stranger can confirm when it was issued:

```sh
export ORC_SEAL_API_KEY=...                # see "Get a registry key" in the main README
python drive.py did:web:yourdomain.com
orc-seal verify receipt.json               # -> ISSUED
```

Only the commitment, digest, salt, profile and tool name are sent. Outputs and
arguments never are.

Two things to know:

- Use your own issuer id. `did:web:viridisconservation.com` is reserved and the
  registry refuses it.
- If registration fails, the result still comes back sealed as INTACT, and
  `orc-seal` (0.1.1 and later) says why once on stderr.

To wrap your own server, replace the command after `--` in your MCP client
config, as shown in the main README.
