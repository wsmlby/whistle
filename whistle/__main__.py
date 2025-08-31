import click
import whistle.config as config
import whistle.llm as llm
import whistle.alert as alert_util
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
ExecStart={exec_path} monitor
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
@click.option('--max_log_length', type=int, help='Maximum log length to send to LLM.')
@click.option('--show', is_flag=True, help='Show current LLM config values.')
def config_llm(base_url, api_key, model, max_log_length, show):
    """Configure the LLM or show current config."""
    conf = config.load_config()
    if show:
        click.echo("Current LLM config:")
        click.echo(json.dumps(conf.get('llm', {}), indent=2))
        click.echo(f"llm_max_log_length: {conf.get('llm_max_log_length', 256)}")
        return
    if base_url is not None:
        conf['llm']['base_url'] = base_url
    if api_key is not None:
        conf['llm']['api_key'] = api_key
    if model is not None:
        conf['llm']['model'] = model
    if max_log_length is not None:
        conf['llm_max_log_length'] = max_log_length
    config.save_config(conf)
    click.echo("LLM configuration updated.")


@config_group.command(name='alert')
@click.option('--slack', 'slack_webhook_url', help='The Slack webhook URL.')
@click.option('--show', is_flag=True, help='Show current alert config values.')
def config_alert(slack_webhook_url, show):
    """Configure alerting or show current config."""
    conf = config.load_config()
    if show:
        click.echo("Current alert config:")
        click.echo(json.dumps(conf.get('alert', {}), indent=2))
        return
    if slack_webhook_url is not None:
        conf['alert']['slack'] = slack_webhook_url
    config.save_config(conf)
    click.echo("Alerting configuration updated.")


@config_group.command(name='log')
@click.option('--kernel_only', type=click.BOOL, help='Whether to watch only kernel messages.')
@click.option('--service_unit', 'service_units', multiple=True, help='A systemd service unit to watch. Can be specified multiple times.')
@click.option('--show', is_flag=True, help='Show current log config values.')
def config_log(kernel_only, service_units, show):
    """Configure logging or show current config."""
    conf = config.load_config()
    if show:
        click.echo("Current log config:")
        click.echo(json.dumps(conf.get('log', {}), indent=2))
        return
    if kernel_only is not None:
        conf['log']['kernel_only'] = kernel_only
    if service_units:
        conf['log']['service_units'] = list(service_units)
    config.save_config(conf)
    click.echo("Log configuration updated.")


# Test command: analyze sample logs and optionally trigger alert
@cli.command()
@click.option('--alert', is_flag=True, help='If set, also send a test alert.')
def test(alert):
    """Test log analysis and alerting."""
    from whistle.test_cases import test_cases
    conf = config.load_config()
    click.echo("Current configuration:")
    click.echo(json.dumps(conf, indent=4))

    click.echo("\nAnalyzing test logs...")
    ignore_regexes = []
    for case in test_cases:
        entry = case["log"]
        analysis = llm.analyze_log(entry, conf)
        click.echo(f"Log: {entry}")
        click.echo(f"Analysis: {json.dumps(analysis, indent=2)}")
        mismatch = False
        # Update local ignore regex list if suggested
        if analysis.get('ignore_regex'):
            if analysis['ignore_regex'] not in ignore_regexes:
                ignore_regexes.append(analysis['ignore_regex'])
        # Check ignored expectation
        if case.get('expect_ignored', False):
            import re
            ignored = any(re.search(regex, entry) for regex in ignore_regexes)
            if not ignored:
                mismatch = True
                click.secho("Expected log to be ignored by ignore rules, but it was not.", fg='red')
            if ignored and not mismatch:
                click.secho("Log was correctly ignored by ignore rules.", fg='green')
                continue
        # Check anomaly expectation
        if 'expect_anomaly' in case:
            if analysis.get('is_anomaly', False) != case.get('expect_anomaly', False):
                mismatch = True
                click.secho(f"Expected anomaly: {case.get('expect_anomaly', False)}, got: {analysis.get('is_anomaly', False)}", fg='red')
            # Check reason expectation
            if case.get('expect_anomaly', False) and case.get('expect_reason_contains'):
                reason = analysis.get('reason', '')
                expected = case['expect_reason_contains']
                if isinstance(expected, str):
                    expected = [expected]
                if not any(e in reason for e in expected):
                    mismatch = True
                    click.secho(f"Expected reason to contain one of {expected}, got: '{reason}'", fg='red')
        if not mismatch:
            click.secho("Behavior as expected.", fg='green')
        if analysis.get('is_anomaly') and alert:
            click.secho("--- ALERT TRIGGERED ---", fg='yellow')
            alert_util.send_alert(f"[TEST]Anomaly detected: {entry}\nReason: {analysis.get('reason', '')}", conf)
        click.echo("---")



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

@ignore.command(name="delete")
@click.argument('name')
def ignore_delete(name):
    """Delete an ignore rule by name."""
    conf = config.load_config()
    before = len(conf.get('ignore', []))
    conf['ignore'] = [r for r in conf.get('ignore', []) if r['name'] != name]
    after = len(conf['ignore'])
    config.save_config(conf)
    if before == after:
        click.echo(f"No ignore rule found with name '{name}'.")
    else:
        click.echo(f"Ignore rule '{name}' deleted.")

@ignore.command(name="delete-all")
@click.option('--yes', is_flag=True, help='Skip confirmation prompt.')
def ignore_delete_all(yes):
    """Delete all ignore rules."""
    if not yes:
        if not click.confirm("Are you sure you want to delete ALL ignore rules?", default=False):
            click.echo("Delete-all cancelled.")
            return
    conf = config.load_config()
    conf['ignore'] = []
    config.save_config(conf)
    click.echo("All ignore rules deleted.")


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
@click.option('--show-ignored', is_flag=True, help="Show ignored log entries.")
def analyze(since, show_ignored):
    """Analyze logs since a given time."""
    try:
        conf = config.load_config()
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
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

    if not click.confirm(f"Proceed to analyze {len(log_entries)} log entries?", default=True):
        click.echo("Analysis cancelled by user.")
        return

    import re
    num_anomalies = 0
    # Always reload ignore list from config at the beginning
    ignore_list = config.load_config().get('ignore', [])
    new_ignore_list_count = 0
    ignored_log_count = 0
    analysis_run_count = 0
    for entry in log_entries:
        if not entry:
            continue
        # Check if entry matches any ignore rule
        ignored = any(re.search(r.get('regex'), entry) for r in ignore_list)
        if ignored:
            if show_ignored:
                click.secho(f"IGNORED: {entry}", fg='yellow')
            ignored_log_count += 1
            continue
        
        analysis = llm.analyze_log(entry, conf)
        click.secho(f"Analyzing log entry: {entry} got {analysis}", fg='blue')
        analysis_run_count += 1
        # If new ignore_regex is suggested, add to ignore list
        if analysis.get('ignore_regex'):
            new_regex = analysis['ignore_regex']
            if not any(r.get('regex') == new_regex for r in ignore_list):
                rule_name = analysis.get("ignore_regex_name", f"llm-suggested-{int(time.time())}")
                new_rule = {
                    "name": rule_name,
                    "regex": new_regex,
                    "comment": f"Auto-suggested by LLM for log: {entry[:50]}..."
                }
                ignore_list.append(new_rule)
                conf['ignore'] = ignore_list
                new_ignore_list_count += 1
                try:
                    config.save_config(conf)
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
    click.secho(f"Total ignored rules: {len(ignore_list)}", fg='yellow')
    click.secho(f"Total ignored logs: {ignored_log_count}", fg='yellow')
    click.secho(f"Total new ignore rules added: {new_ignore_list_count}", fg='yellow')
    click.secho(f"Total log entries analyzed with LLM: {analysis_run_count}", fg='yellow')

@cli.command()
def monitor():
    """Monitor logs in real-time and trigger alerts."""

    try:
        conf = config.load_config()
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
                        config.save_config(conf)
                        click.secho(f"New ignore rule '{rule_name}' automatically added for regex: '{new_regex}'", fg='green')
                    except Exception as e:
                        click.secho(f"Failed to save new ignore rule: {e}", fg='red')

            if analysis['is_anomaly']:
                click.echo("---")
                click.secho(f"Anomaly detected: {analysis['reason']}", fg='red')
                click.echo(entry)
                # Here we would trigger a notification
                alert_util.send_alert(f"Anomaly detected: {entry}\nReason: {analysis.get('reason', '')}", conf)

    except FileNotFoundError:
        click.echo(f"Error: 'journalctl' command not found. Please make sure systemd is installed.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"An error occurred: {e}", err=True)
        sys.exit(1)
    finally:
        if process:
            process.terminate()

@ignore.command(name="smart_combine")
def ignore_smart_combine():
    """Suggest a smart combination of ignore rules using LLM."""
    conf = config.load_config()
    rules = conf.get('ignore', [])
    if not rules:
        click.echo("No ignore rules to combine.")
        return
    from whistle.llm import summarize_ignore_rules
    click.echo("Combining ignore rules using LLM...")
    combined = summarize_ignore_rules(rules, conf)
    if not combined:
        click.secho("No combined rules returned or LLM not configured.", fg='red')
        return
    click.echo("Suggested combined ignore rules:")
    for rule in combined:
        click.echo(json.dumps(rule, indent=2))
    click.secho(f"Combining ignore rules from {len(rules)} to {len(combined)}.", fg='green')
    if not click.confirm("Do you want to save these changes?", default=False):
        click.echo("Changes not saved.")
        return
    conf['ignore'] = combined
    try:
        config.save_config(conf)
        click.secho("Configuration updated successfully.", fg='green')
    except Exception as e:
        click.secho(f"Failed to save configuration: {e}", fg='red')

if __name__ == '__main__':
    cli()
