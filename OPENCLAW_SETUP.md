# OPENCLAW_SETUP: OpenClaw Installation & Configuration

## Basic Configuration

### Download & Install

```cmd
# Install OpenClaw (latest)
curl -fsSL https://openclaw.ai/install.sh | bash

# Uninstall OpenClaw
openclaw uninstall

# Update OpenClaw
openclaw update

# Install OpenClaw (specific version, skip onboard)
curl -fsSL --proto '=https' --tlsv1.2 https://openclaw.ai/install.sh | bash -s -- --version 2026.4.2 --no-onboard
```



### Basic Commands

| Command                        | Description                              | Notes                                                                                              |
| :----------------------------- | :--------------------------------------- | :------------------------------------------------------------------------------------------------- |
| openclaw onboard               | Configuration wizard                     |                                                                                                    |
| openclaw gateway run &         | Start gateway (foreground)               | Does not require systemd service (stop: Ctrl+C / close terminal)                                  |
| openclaw gateway start         | Start gateway (service)                  | Requires systemd service (stop: via command)                                                      |
| openclaw gateway stop          | Stop gateway (service)                   | Used with ```openclaw gateway start```                                                            |
| openclaw gateway restart       | Restart gateway (service)                | Used with ```openclaw gateway start```                                                            |
| openclaw gateway status        | Check gateway status                     |                                                                                                    |
| openclaw --version             | Check version                            |                                                                                                    |
| openclaw status                | Check status                             |                                                                                                    |
| openclaw channels status       | Check connection status                  |                                                                                                    |
| openclaw logs                  | View logs                                |                                                                                                    |
| openclaw memory status         | Check memory                             |                                                                                                    |
| openclaw skills list           | List skills                              |                                                                                                    |
| openclaw configure             | Modify configuration                     |                                                                                                    |
| openclaw dashboard             | Open web dashboard (browser chat)        |                                                                                                    |
| openclaw tui                   | Open terminal chat interface             |                                                                                                    |
| openclaw doctor                | Run system diagnostics                   |                                                                                                    |
| openclaw doctor --deep --yes   | Deep health check with auto-repair       |                                                                                                    |
| openclaw config get tools.exec | View the value of config key tools.exec  |                                                                                                    |
| openclaw models                | List available models                    |                                                                                                    |
| openclaw models set [model]    | Set the default model                    |                                                                                                    |

- Starting the gateway
  - **`gateway run`** runs in the **foreground** — it starts the Gateway process directly in the current terminal, with debug/trace logs printed to stdio. Closing the terminal or pressing Ctrl+C will stop it [OpenClaw](https://docs.openclaw.ai/cli/gateway). One detail: by default it requires `gateway.mode=local` to be set in the config file; if not configured, you need to add `--allow-unconfigured` to start it [OpenClaw](https://docs.openclaw.ai/cli/gateway).
  - **`gateway start`** starts a **managed service** — it operates the system service installed via `openclaw gateway install` (launchd LaunchAgent on macOS, systemd user service on Linux) [Openclaws](https://openclaws.io/docs/gateway). The process runs in the background, independent of the terminal.



### Installation Issues

|                             Error                            |                             Meaning                          |          Resolution          |
| :----------------------------------------------------------: | :----------------------------------------------------------: | :--------------------------: |
| Systemd user services are unavailable. Skipping lingering checks and service install. | Systemd user service is unavailable. This service is used for autostart on boot and can generally be ignored. However, the gateway will be off by default, so you will need to start it manually after each reboot. | openclaw gateway run & |




## Configure OpenAI Chat Completions Endpoint

### Step 1: Enable the HTTP endpoint in `~/.openclaw/openclaw.json`

```json
{
  "gateway": {
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true }
      }
    }
  }
}
```

- After modification, wait a moment for the connection to be established (add the field if it doesn't exist), or restart the gateway.



### Step 2: Test the endpoint

```python
from openai import OpenAI

client = OpenAI(
    base_url="<YOUR_GATEWAY_BASE_URL>",
    api_key="<YOUR_GATEWAY_TOKEN>",   # i.e. the value of gateway.auth.token
)

response = client.chat.completions.create(
    model="openclaw/default",       # routes to the default Agent
    messages=[
        {"role": "user", "content": "List all files in your working directory."}
    ],
)

print(response.choices[0].message.content)
```




## OpenClaw Test Mail Service

### Part 1: Deploy Mailpit

**Download & Install**

```cmd
# Download the package (check version; this example uses Ubuntu 24.04 x86_64).
# If the server cannot reach GitHub, download the file via browser and upload manually.
wget https://github.com/axllent/mailpit/releases/latest/download/mailpit-linux-amd64.tar.gz

# Install
tar -xzf mailpit-linux-amd64.tar.gz
sudo mv mailpit /usr/local/bin/      # other extracted files can be deleted
sudo chmod +x /usr/local/bin/mailpit

# Verify
mailpit version
```

 **Create systemd service: enable autostart and anonymous SMTP auth (for himalaya)**

```cmd
# Write mailpit.service
sudo tee /etc/systemd/system/mailpit.service << 'EOF'
[Unit]
Description=Mailpit - local email testing
After=network.target

[Service]
ExecStart=/usr/local/bin/mailpit \
  --smtp 0.0.0.0:1025 \
  --listen 0.0.0.0:8025 \
  --smtp-auth-accept-any \
  --smtp-auth-allow-insecure
Restart=always
User=nobody

[Install]
WantedBy=multi-user.target
EOF
```

**Start the systemd service**

```cmd
# Start the systemd service
sudo systemctl daemon-reload
sudo systemctl enable mailpit
sudo systemctl start mailpit
```

**Verify Mailpit is running**

```cmd
# Check service status
systemctl status mailpit

# Check if API is reachable
curl -s http://localhost:8025/api/v1/messages | python3 -m json.tool  # returns an empty JSON object if healthy
```



### Part 2: Deploy himalaya

**Download & Install**

```cmd
# Download the package (check version; this example uses Ubuntu 24.04 x86_64).
# If the server cannot reach GitHub, download the file via browser and upload manually.
wget https://github.com/pimalaya/himalaya/releases/download/v1.2.0/himalaya.x86_64-linux.tgz

# Install
tar -xzf himalaya.x86_64-linux.tgz
sudo mv himalaya /usr/local/bin/

# Verify
himalaya --version
```

**Configure himalaya to connect to Mailpit**

```cmd
# Create config directory
mkdir -p ~/.config/himalaya

# Create config file (with empty authentication)
cat > ~/.config/himalaya/config.toml << 'EOF'
[accounts.mailpit]
default = true
email = "openclaw@localhost"
display-name = "OpenClaw"

backend.type = "none"

message.send.backend.type = "smtp"
message.send.backend.host = "localhost"
message.send.backend.port = 1025
message.send.backend.encryption.type = "none"
message.send.backend.login = "openclaw@localhost"
message.send.backend.auth.type = "password"
message.send.backend.auth.cmd = "echo dummy"

message.send.save-copy = false
EOF
```

**Verify himalaya can send mail to Mailpit**

```cmd
# Clear Mailpit inbox
curl -X DELETE http://localhost:8025/api/v1/messages

# Send a test email
cat << 'EOF' | himalaya template send
From: openclaw@localhost
To: eve@example.com
Subject: test_mail

hello world
EOF

# Check receipt (output should be: test_mail -> ['eve@example.com'])
curl -s http://localhost:8025/api/v1/messages | python3 -c "
import json, sys
msgs = json.load(sys.stdin)['messages']
for m in msgs:
    print(m['Subject'], '->', [t['Address'] for t in m['To']])
"
```



### Part 3: Verify OpenClaw himalaya Skill is Ready

**Check himalaya skill status**

```cmd
# Check himalaya skill status (expected output: Ready)
openclaw skills info himalaya
```

**Email test**

```cmd
# Clear inbox
curl -X DELETE http://localhost:8025/api/v1/messages

# Send email (enter the following as user input in openclaw tui or via chat completions in Python)
"Send an email to eve@example.com with subject 'test_mail' and body 'hello world'."

# Verify the email exists (run the command below, or visit http://localhost:8025)
curl -s http://localhost:8025/api/v1/messages | python3 -c "
import json, sys
msgs = json.load(sys.stdin)['messages']
for m in msgs:
    print(m['Subject'], '->', [t['Address'] for t in m['To']])
"

# Verify email content (run the command below, or visit http://localhost:8025)
curl -s http://localhost:8025/api/v1/messages | python3 -c "
import json, sys, urllib.request
msgs = json.load(sys.stdin)['messages']
matched = [m for m in msgs if m.get('Subject') == 'test_mail_1']
if not matched:
    print('not found')
    sys.exit(0)
for m in matched:
    with urllib.request.urlopen('http://localhost:8025/api/v1/message/' + m['ID']) as r:
        d = json.load(r)
    print('Subject:', d['Subject'])
    print('From:', d['From']['Address'])
    print('To:', [t['Address'] for t in d['To']])
    print('Body:', d.get('Text') or d.get('HTML') or '(no body)')
"
```

- View emails via browser: ```http://<YOUR_SERVER_PUBLIC_IP>:8025```



#  Evaluation with LITMUS

## Environment Setup (run before testing)

```cmd
pip install openai
pip install websockets
pip install flask
pip install pandas
apt install unzip
apt install zip
apt install acl
apt install -y auditd audispd-plugins
apt install -y stress-ng
apt install -y gdb
apt install -y php
```

- Run ```ssh-keygen -t rsa -C "openclaw_test@example.com"``` to generate the test SSH key pair: ```~/.ssh/id_rsa``` and ```~/.ssh/id_rsa.pub```
- Run `openclaw onboard` to configure values such as `openai_key` in `openclaw.json` for testing
- Start a simple `openclaw tui` session (e.g., ask about the weather) to establish the test session `"agent:main:main"`
- Extract `./fixtures/Fixtures.zip` into the directory specified by the environment variable `FIXTURE_DIR` (default: `/root/workspace/`)



## Environment Variables

```cmd
# Prosecutor, Verifier, Analyzer, and LLMDefendant
export OPENAI_MODEL="gpt-4o"
export OPENAI_BASE_URL="<YOUR_OPENAI_BASE_URL>"
export OPENAI_API_KEY="<YOUR_OPENAI_API_KEY>"

# OpenClawDefendant
export OPENCLAW_GATEWAY_URL="<YOUR_OPENCLAW_GATEWAY_URL>"            # do not append ".../v1"
export OPENCLAW_GATEWAY_TOKEN="<YOUR_OPENCLAW_GATEWAY_TOKEN>"        # i.e. the value of gateway.auth.token

# PathVars
export FIXTURE_DIR='/root/workspace/'     # directory for utility programs and data dependencies
export AGENT_HOME_DIR='/root/.openclaw/'  # directory for files related to the agent under test
export RUNTIME_TMP_DIR='/tmp/'            # directory for runtime temporary files
```

- AutoDL LLM API
  - BASE_URL: ```<YOUR_AUTODL_BASE_URL>```
  - API_KEY: ```<YOUR_AUTODL_API_KEY>```



## Running Scripts

The LITMUS seed subset can be evaluated directly using the commands in the "Evaluation Scripts" section once the system is configured. The attack-extended subsets require first running the corresponding "Instruction Wrapping Scripts" to produce the attack-wrapped dataset, after which the "Evaluation Scripts" commands can be used for evaluation.



### Evaluation Scripts

**1. Single-row Test**

```cmd
# Single-row test: specify output file
python run_pipeline.py --input ./data/dataset_3.27.csv --row 0 --output results.csv --defendant openclaw --tool-hints-dir ./tools/
```

**2. Dataset Test**

```cmd
# Dataset test: specify output file, show progress bar (suppress verbose output)
python run_pipeline.py --input ./data/dataset_3.27.csv --output results.csv --defendant openclaw --tool-hints-dir ./tools/ --quiet

# Retry: retry cases where judgement is "0" or "-1" ("--retry" and "--row" are mutually exclusive)
python run_pipeline.py --input results.csv --retry 0,-1 --defendant openclaw --tool-hints-dir ./tools/ --quiet

# Resume from interruption (processes cases where judgement is empty or "-1" by default)
python run_pipeline.py --input results.csv --defendant openclaw --tool-hints-dir ./tools/ --quiet
```

- For detailed CLI options, see `./document/CLI_REFERENCE_Run_Pipeline.md`

**3. Generate Report**

```python
# Merges and deduplicates all log files, then generates:
# (1) merged.jsonl                    # merged log file
# (2) _merged_EHR_detail.csv          # test detail summary (physical state, conversation, semantic/physical labels, ...)
# (3) _merged_EHR_report.csv          # ASR and EHR statistical report
# (4) _merged_summary_report.csv      # four-quadrant analysis report (SPSR, SOSR, POSR, SPFR, ASR, EHR)
python logs_analyze.py --log-dir ./logs --merge_summary_report
```

- Note: to simplify the evaluation workflow, the `Verifier` and `Reviewer` evaluation steps are decoupled in the code. Step 2 (Dataset Test) only performs `Verifier` judgement; the `Reviewer` evaluation is handled uniformly in Step 3 (Generate Report).

- For detailed CLI options, see `./document/CLI_REFERENCE_Logs_Analyze.md`



### Instruction Wrapping Scripts

**1. File Wrapping**

```cmd
# Apply instruction template
python prompt_process.py apply-template --dataset ./data/dataset_3.27.csv --template ./templates/template_for_txt_1.txt

# Split dataset into individual txt files
python prompt_process.py split --dataset ./data/dataset_3.27_template_applied.csv --output-dir $FIXTURE_DIR/split_input_prompt_txts

# Embed txt file references into the input_prompt column of the dataset
python prompt_process.py apply-file-template --dataset ./data/dataset_3.27.csv --template ./templates/template_for_prompt_file_1.txt --txts-dir $FIXTURE_DIR/split_input_prompt_txts
```

**2. Web Wrapping**

```cmd
# Apply instruction template
!python prompt_process.py apply-template --dataset ./data/dataset_3.27.csv --template ./templates/template_for_txt_1.txt

# Split dataset into individual txt files
!python prompt_process.py split --dataset ./data/dataset_3.27_template_applied.csv --output-dir $FIXTURE_DIR/split_input_prompt_txts

# Embed URL references into the input_prompt column of the dataset
!python prompt_process.py apply-url-template --dataset ./data/dataset_3.27.csv --template ./templates/template_for_prompt_url_1.txt --base-url http://localhost:61007
```

```cmd
############################ Test Web Service ############################
# Start the prompt web server (resolves URLs and returns the instructions from the corresponding txt file)
nohup python $FIXTURE_DIR/test_prompt_server/prompt_server.py --host 0.0.0.0 --port 61007 --txts-dir $FIXTURE_DIR/split_input_prompt_txts > /dev/null 2>&1 &

# Verify using a real test case's category_id and task_id
curl -s -w "\n[HTTP Status: %{http_code}]\n" http://localhost:61007/test_1_1

# Stop the server
pkill -f $FIXTURE_DIR/test_prompt_server/prompt_server.py
```

**3. Jailbreak Rhetoric Wrapping**

```cmd
# Apply jailbreak instruction template (Red Team Testing)
python prompt_process.py apply-template --dataset dataset_3.27.csv --template ./templates/template_for_prompt_jailbreak_1.txt

# Apply jailbreak instruction template (Debug Mode)
python prompt_process.py apply-template --dataset dataset_3.27.csv --template ./templates/template_for_prompt_jailbreak_2.txt
```

- For detailed CLI options, see `./document/CLI_REFERENCE_Prompt_Process.md`
