import click
import whistle.config as config
import whistle.llm as llm
import json
import os
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
def test(alert):
    """Test the configuration."""
    conf = config.load_config()
    click.echo("Current configuration:")
    click.echo(json.dumps(conf, indent=4))

    if alert:
        click.echo("\n--alert flag is set. In the future, this will send a test alert.")


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

    # Create config directory and default config
    config_dir = Path("/etc/whistle")
    config_file = config_dir / "config.json"

    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        if not config_file.exists():
            click.echo(f"Creating default config at {config_file}")
            with open(config_file, 'w') as f:
                json.dump(config.DEFAULT_CONFIG, f, indent=4)
        else:
            click.echo(f"Config file {config_file} already exists. Skipping creation.")
    except Exception as e:
        click.echo(f"Error creating config file: {e}", err=True)
        sys.exit(1)


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
def analyze(since):
    """Analyze logs since a given time."""
    conf = config.load_config()

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
