# Mac (launchd) fallback — run the weekly job on your own machine

Use this if GitHub Actions gets bot-blocked on Chinese news sites (datacenter
IPs are throttled more than home connections). Running on your Mac uses your home
IP, which those sites generally allow.

## One-time setup

1. Put your key in the repo's `.env` (copy `.env.example`), e.g.:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   HWC_EXTRACT_MODEL=claude-haiku-4-5
   GEOCODE_CONTACT_EMAIL=you@example.com
   ```
2. Create the launch agent file at
   `~/Library/LaunchAgents/com.rolandkays.hwcmonitor.plist` with this content
   (edit the two paths to match your machine):

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0"><dict>
     <key>Label</key><string>com.rolandkays.hwcmonitor</string>
     <key>ProgramArguments</key>
     <array>
       <string>/bin/bash</string>
       <string>/Users/rwkays/claude_code/chineseHWC/run_weekly.sh</string>
     </array>
     <key>StartCalendarInterval</key>
     <dict><key>Weekday</key><integer>1</integer>
           <key>Hour</key><integer>9</integer>
           <key>Minute</key><integer>0</integer></dict>
     <key>StandardOutPath</key><string>/Users/rwkays/claude_code/chineseHWC/data/weekly.log</string>
     <key>StandardErrorPath</key><string>/Users/rwkays/claude_code/chineseHWC/data/weekly.err</string>
     <key>WorkingDirectory</key><string>/Users/rwkays/claude_code/chineseHWC</string>
   </dict></plist>
   ```
   This runs every Monday at 09:00 local time.

3. Load it:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.rolandkays.hwcmonitor.plist
   ```
   Test immediately with:
   ```bash
   launchctl start com.rolandkays.hwcmonitor
   tail -f data/weekly.log
   ```

## After a Mac run

`run_weekly.sh` updates `data/master/incidents.csv` and `docs/index.html`
locally. To publish, commit and push:
```bash
cd /Users/rwkays/claude_code/chineseHWC
git add data/master/incidents.csv docs/index.html
git commit -m "weekly update (local run)"
git push
```
GitHub Pages then republishes automatically.

## Choosing between GitHub and Mac

- **Default: GitHub Actions.** Zero effort; runs even when your Mac is off.
- **Switch to Mac** if the weekly issue/log shows many `blocked` fetches from a
  site you care about. You can run *both* — they dedup against the same master,
  so nothing is double-counted.
- To pause GitHub while using the Mac, disable the workflow in the repo's
  Actions tab (or comment out the `schedule:` block).
