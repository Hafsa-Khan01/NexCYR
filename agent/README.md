# NexCYR Local Agent

The NexCYR Agent is the local execution node for an authorized network. It lets the Railway Cloud command center use the real network and Wi-Fi interfaces without pretending those interfaces exist inside the cloud container.

## What it provides

- Nmap host discovery for authorized IP/network targets
- Nmap top-100 port scanning
- Nmap service/version enumeration
- Passive Windows Wi-Fi telemetry using `netsh`
- Local Wi-Fi interface, connected SSID, visible SSIDs/BSSIDs, signal/channel/security data
- Heartbeats so the Cloud knows the Agent is actually online

The Agent accepts only NexCYR's predefined job types. It does not accept arbitrary shell commands.

## Setup on the authorized operator machine

1. Install Nmap and make sure `nmap` is available in PATH.
2. From the NexCYR repository root, install the Python dependency:

```powershell
python -m pip install requests
```

3. In NexCYR, open **NexCYR Agents** and create an enrollment.
4. Copy the one-time enrollment token.
5. Start the Agent:

```powershell
python agent\nexcyr_agent.py --server "https://magnificent-achievement-production.up.railway.app" --token "PASTE_ONE_TIME_TOKEN"
```

Keep that terminal running. The dashboard should show the Agent as **online** and Nmap as **available**.

## Authorized network discovery

Create an explicitly authorized **Network** target, for example:

```text
192.168.1.0/24
```

Select the online Agent as the scanner and run **Basic Scan**. For a network target, Basic Scan is routed to Nmap host discovery and returns the live devices found in that authorized network.

For deeper assessment, run **Nmap service / version** against the same authorized network through the Agent. The central NexCYR risk engine creates findings from the structured service results.

## Wi-Fi discovery

The Agent reports a passive Wi-Fi snapshot in its heartbeat. The Wi-Fi Security screen can then use the Agent's real local wireless interface instead of the Railway container's missing `iw`/Wi-Fi interface.

This is observational only: no deauthentication, injection, credential capture, or disruptive wireless activity is performed.

## Stop

Press:

```
Ctrl+C
```

The Cloud will eventually show the Agent as offline after heartbeats become stale.
