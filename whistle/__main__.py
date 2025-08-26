import click
import whistle.config as config
import whistle.llm as llm
import json
import os
import time
import shutil
import subprocess
import sys
from pathlib import Path

SERVICE_FILE_CONTENT = """
[Unit]
Description=WhistleAI Log Monitoring Service
After=network.target

[Service]
Type=simple
User=root
ExecStart={exec_path} monitor --config /etc/whistle/config.json
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""

@click.group()
def cli():
    """WhistleAI: A lightweight, intelligent log monitoring tool."""
    pass

@cli.group(name="config")
def config_group():
    """Manage configuration."""
    pass

@config_group.command(name='llm')
@click.option('--base_url', help='The base URL for the LLM API.')
@click.option('--api_key', help='The API key for the LLM API.')
@click.option('--model', help='The model to use for the LLM.')
def config_llm(base_url, api_key, model):
    """Configure the LLM."""
    conf = config.load_config()
    if base_url is not None:
        conf['llm']['base_url'] = base_url
    if api_key is not None:
        conf['llm']['api_key'] = api_key
    if model is not None:
        conf['llm']['model'] = model
    config.save_config(conf)
    click.echo("LLM configuration updated.")

@config_group.command(name='alert')
@click.option('--slack', 'slack_webhook_url', help='The Slack webhook URL.')
def config_alert(slack_webhook_url):
    """Configure alerting."""
    conf = config.load_config()
    if slack_webhook_url is not None:
        conf['alert']['slack'] = slack_webhook_url
    config.save_config(conf)
    click.echo("Alerting configuration updated.")

@config_group.command(name='log')
@click.option('--kernel_only', type=click.BOOL, help='Whether to watch only kernel messages.')
@click.option('--service_unit', 'service_units', multiple=True, help='A systemd service unit to watch. Can be specified multiple times.')
def config_log(kernel_only, service_units):
    """Configure logging."""
    conf = config.load_config()
    if kernel_only is not None:
        conf['log']['kernel_only'] = kernel_only
    if service_units:
        conf['log']['service_units'] = list(service_units)
    config.save_config(conf)
    click.echo("Log configuration updated.")


@cli.command()
@click.option('--alert', is_flag=True, help='If set, also send a test alert.')
@click.option('--llm', 'test_llm', is_flag=True, help='If set, also test the LLM connection and logic.')
def test(alert, test_llm):
    """Test the configuration."""
    conf = config.load_config()
    click.echo("Current configuration:")
    click.echo(json.dumps(conf, indent=4))

    if alert:
        click.echo("\n--alert flag is set. In the future, this will send a test alert.")

    if test_llm:
        click.echo("\n--- Testing LLM configuration ---")
        llm_config = conf.get('llm', {})
        api_key = llm_config.get('api_key')
        model = llm_config.get('model')

        if not all([api_key, model]):
            click.secho("LLM is not configured. Please run 'whistle config llm' first.", fg='red')
            return

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=llm_config.get('base_url'))

            # 1. Test basic API connection
            click.echo("1. Testing API connection...")
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=5,
            )
            click.secho("   API connection successful.", fg='green')

            # 2. Test analysis logic with predefined logs
            click.echo("\n2. Testing analysis logic with example logs...")
            EXAMPLE_LOGS = [
                {
                    "description": "Critical Error (Should be an Anomaly)",
                    "log": "systemd[1]: Failed to start My Important Service.",
                },
                {
                    "description": "Informational Message (Should not be an Anomaly)",
                    "log": "kernel: usb 1-1: new high-speed USB device number 9 using xhci_hcd",
                },
                {
                    "description": "Repetitive Warning (Should suggest an ignore rule)",
                    "log": "sshd[12345]: Connection from 192.168.1.100 port 22: invalid user john",
                },
            ]

            for item in EXAMPLE_LOGS:
                click.echo(f"\n--- Case: {item['description']} ---")
                click.echo(f"   Log Entry: {item['log']}")

                # We pass the real config, so it will respect the ignore list if any matches
                analysis = llm.analyze_log(item['log'], conf)

                click.secho("   LLM Analysis:", fg='yellow')
                click.echo(f"     Is Anomaly: {analysis.get('is_anomaly')}")
                click.echo(f"     Reason: {analysis.get('reason')}")
                click.echo(f"     Ignore Regex: {analysis.get('ignore_regex')}")

        except Exception as e:
            click.secho(f"LLM test failed: {e}", fg='red')


@cli.group()
def ignore():
    """Manage ignore list."""
    pass

@ignore.command(name="list")
def ignore_list():
    """List all ignore rules."""
    conf = config.load_config()
    if not conf.get('ignore'):
        click.echo("No ignore rules defined.")
        return

    for rule in conf['ignore']:
        comment_str = f" ({rule.get('comment')})" if rule.get('comment') else ""
        click.echo(f"- {rule['name']}: '{rule['regex']}'{comment_str}")

@ignore.command(name="add")
@click.argument('name')
@click.argument('regex')
@click.option('--comment', help='A comment for the ignore rule.')
def ignore_add(name, regex, comment):
    """Add a new ignore rule."""
    conf = config.load_config()

    if any(r['name'] == name for r in conf['ignore']):
        click.echo(f"Error: Ignore rule with name '{name}' already exists.", err=True)
        raise click.Abort()

    new_rule = {'name': name, 'regex': regex}
    if comment:
        new_rule['comment'] = comment

    conf['ignore'].append(new_rule)
    config.save_config(conf)
    click.echo(f"Ignore rule '{name}' added.")


@cli.group()
def service():
    """Manage the WhistleAI service."""
    pass

@service.command()
def install():
    """Install the WhistleAI systemd service."""
    if os.geteuid() != 0:
        click.echo("Error: This command must be run as root.", err=True)
        sys.exit(1)

    click.echo("Installing WhistleAI service...")

    # Find whistle executable
    whistle_path = shutil.which('whistle')
    if not whistle_path:
        click.echo("Error: 'whistle' executable not found in PATH.", err=True)
        click.echo("Please make sure the package is installed correctly.", err=True)
        sys.exit(1)

    click.echo(f"Found whistle executable at: {whistle_path}")

    # --- Configuration Setup ---
    config_dir = Path("/etc/whistle")
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"

    # Load user's local config to offer it as the system config
    user_conf = config.load_config()

    click.echo("\n--- Configuration Setup ---")
    if click.confirm(f"Do you want to copy your local user configuration from '{config.CONFIG_FILE}' to the system-wide path '{config_file}'?", default=True):
        try:
            click.echo(f"Copying config to {config_file}...")
            config.save_config(user_conf, path=str(config_file))
            click.secho("Successfully copied configuration.", fg='green')
        except Exception as e:
            click.secho(f"Error copying config file: {e}", fg='red')
            sys.exit(1)
    else:
        # If user declines, create a default config if one doesn't exist
        if not config_file.exists():
            click.echo(f"Creating default config at {config_file}")
            try:
                config.save_config(config.DEFAULT_CONFIG, path=str(config_file))
            except Exception as e:
                click.secho(f"Error creating default config file: {e}", fg='red')
                sys.exit(1)
        else:
            click.echo(f"Keeping existing config file at {config_file}.")


    # Create systemd service file
    service_file_path = Path("/etc/systemd/system/whistle-ai.service")
    service_content = SERVICE_FILE_CONTENT.format(exec_path=whistle_path)

    try:
        click.echo(f"Creating systemd service file at {service_file_path}")
        with open(service_file_path, "w") as f:
            f.write(service_content)
    except Exception as e:
        click.echo(f"Error creating systemd service file: {e}", err=True)
        sys.exit(1)

    # Reload systemd
    try:
        click.echo("Reloading systemd daemon...")
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
    except Exception as e:
        click.echo(f"Error reloading systemd: {e}", err=True)
        click.echo("Please run 'sudo systemctl daemon-reload' manually.", err=True)
        # Don't exit, the files are created.

    click.echo("\nWhistleAI service installed successfully!")
    click.echo("To start the service, run: sudo systemctl start whistle-ai")
    click.echo("To enable the service to start on boot, run: sudo systemctl enable whistle-ai")


@cli.command()
@click.option('--since', default="1 hour ago", help='The start time for log analysis (e.g., "1 hour ago", "2023-10-27 10:00:00").')
@click.option('--config', 'config_path', help="Path to the configuration file.")
def analyze(since, config_path):
    """Analyze logs since a given time."""
    try:
        conf = config.load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if config_path:
        click.echo(f"Using configuration file: {config_path}")
    click.echo(f"Analyzing logs since '{since}'...")

    # Build journalctl command
    log_entries = []

    if conf['log']['kernel_only']:
        cmd = ['journalctl', '--since', since, '--no-pager', '-k']
        click.echo(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log_entries.extend(result.stdout.strip().split('\n'))
        else:
            click.echo(f"Error reading kernel logs: {result.stderr}", err=True)

    for unit in conf['log'].get('service_units', []):
        cmd = ['journalctl', '--since', since, '--no-pager', '-u', unit]
        click.echo(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log_entries.extend(result.stdout.strip().split('\n'))
        else:
            click.echo(f"Error reading logs for service '{unit}': {result.stderr}", err=True)

    if not log_entries or (len(log_entries) == 1 and not log_entries[0]):
        click.echo("No log entries found for the specified time range and configuration.")
        return

    click.echo(f"\nFound {len(log_entries)} log entries. Analyzing...")

    num_anomalies = 0
    for entry in log_entries:
        if not entry: continue
        analysis = llm.analyze_log(entry, conf)

        if analysis.get('ignore_regex'):
            new_regex = analysis['ignore_regex']
            # Check if this regex is already in the ignore list
            if not any(r.get('regex') == new_regex for r in conf.get('ignore', [])):
                rule_name = f"llm-suggested-{int(time.time())}"
                new_rule = {
                    "name": rule_name,
                    "regex": new_regex,
                    "comment": f"Auto-suggested by LLM for log: {entry[:50]}..."
                }
                conf.setdefault('ignore', []).append(new_rule)
                try:
                    config.save_config(conf, path=config_path)
                    click.secho(f"New ignore rule '{rule_name}' automatically added for regex: '{new_regex}'", fg='green')
                except Exception as e:
                    click.secho(f"Failed to save new ignore rule: {e}", fg='red')

        if analysis['is_anomaly']:
            num_anomalies += 1
            click.echo("---")
            click.secho(f"Anomaly detected: {analysis['reason']}", fg='red')
            click.echo(entry)

    click.echo("---")
    if num_anomalies > 0:
        click.secho(f"\nAnalysis complete. Found {num_anomalies} anomalies.", fg='red')
    else:
        click.secho("\nAnalysis complete. No anomalies found.", fg='green')


@cli.command()
@click.option('--config', 'config_path', help="Path to the configuration file.")
def monitor(config_path):
    """Monitor logs in real-time and trigger alerts."""
    if config_path:
        click.echo(f"Using configuration file: {config_path}")

    try:
        conf = config.load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo("Starting log monitoring...")

    # Build journalctl command
    journal_cmd = ['journalctl', '-f', '--no-pager']
    if conf['log']['kernel_only']:
        journal_cmd.append('-k')
    for unit in conf['log'].get('service_units', []):
        journal_cmd.extend(['-u', unit])

    click.echo(f"Running command: {' '.join(journal_cmd)}")

    process = None
    try:
        process = subprocess.Popen(journal_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        for line in iter(process.stdout.readline, ''):
            entry = line.strip()
            if not entry:
                continue

            analysis = llm.analyze_log(entry, conf)

            if analysis.get('ignore_regex'):
                new_regex = analysis['ignore_regex']
                # Check if this regex is already in the ignore list
                if not any(r.get('regex') == new_regex for r in conf.get('ignore', [])):
                    rule_name = f"llm-suggested-{int(time.time())}"
                    new_rule = {
                        "name": rule_name,
                        "regex": new_regex,
                        "comment": f"Auto-suggested by LLM for log: {entry[:50]}..."
                    }
                    conf.setdefault('ignore', []).append(new_rule)
                    try:
                        config.save_config(conf, path=config_path)
                        click.secho(f"New ignore rule '{rule_name}' automatically added for regex: '{new_regex}'", fg='green')
                    except Exception as e:
                        click.secho(f"Failed to save new ignore rule: {e}", fg='red')

            if analysis['is_anomaly']:
                click.echo("---")
                click.secho(f"Anomaly detected: {analysis['reason']}", fg='red')
                click.echo(entry)
                # Here we would trigger a notification
                click.secho("--- ALERT ---", fg='yellow') # Placeholder for alert

    except FileNotFoundError:
        click.echo(f"Error: 'journalctl' command not found. Please make sure systemd is installed.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An error occurred: {e}", err=True)
        sys.exit(1)
    finally:
        if process:
            process.terminate()


if __name__ == '__main__':
    cli()
