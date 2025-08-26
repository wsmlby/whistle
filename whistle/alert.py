import requests
import json
import click


def send_alert(message, conf):
    """
    Send an alert using the configured method in conf['alert'].
    Currently supports Slack webhook.
    """
    alert_conf = conf.get('alert', {})
    slack_url = alert_conf.get('slack')
    if slack_url:
        payload = {"text": message}
        try:
            resp = requests.post(slack_url, data=json.dumps(payload), headers={"Content-Type": "application/json"})
            if resp.status_code == 200:
                click.secho("Slack alert sent successfully.", fg='green')
            else:
                click.secho(f"Failed to send Slack alert: {resp.text}", fg='red')
        except Exception as e:
            click.secho(f"Error sending Slack alert: {e}", fg='red')
    else:
        click.secho("No alert method configured.", fg='yellow')
