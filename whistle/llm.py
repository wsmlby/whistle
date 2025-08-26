import re
import json
from openai import OpenAI

SYSTEM_PROMPT = """
You are a log analysis expert. Your task is to analyze a given log entry
and determine if it requires a user's attention. The user is a home lab enthusiast. Only alert user for things that are truly concerning. Potential hardware issues should always be flagged.

Analyze the following log entry and respond with a JSON object with four keys:
- "is_anomaly": a boolean (true if it's a critical error, false otherwise).
- "reason": a short, one-sentence explanation for your decision.
- "ignore_regex": a string. If the log entry is not an anomaly but is a common, repetitive message that could be safely ignored in the future, provide a robust regex pattern that would match this type of log entry. Otherwise, this should be null. The regex should be relatively simple and generic.
- "ignore_regex_name": a string. A explanatory name for the ignore regex pattern if provided.
"""

def analyze_log(log_entry: str, config: dict) -> dict:
    """
    Analyzes a single log entry using an LLM and then checks against ignore rules.
    """
    # 1. Get LLM config
    llm_config = config.get('llm', {})
    api_key = llm_config.get('api_key')
    base_url = llm_config.get('base_url')
    model = llm_config.get('model')

    analysis = {}

    if not all([api_key, model]):
        # If LLM is not configured, we can't analyze.
        # Return a default object that won't trigger alerts or new rules.
        return {
            'is_anomaly': False,
            'reason': "LLM is not configured. Skipping analysis.",
            'ignore_regex': None
        }


    # 2. Prepare system prompt with custom rules
    custom_rules = config.get('custom_rules', [])
    custom_rules_str = ""
    if custom_rules:
        custom_rules_str = "\n\nCustom rules to consider:\n" + "\n".join(f"- {rule}" for rule in custom_rules)
    system_prompt = SYSTEM_PROMPT + custom_rules_str
    if len(log_entry) > config.get('llm_max_log_length', 256):
        log_entry = log_entry[:config['llm_max_log_length'] - len("::TRUNCATED")] + "::TRUNCATED"
    # 3. Call LLM API
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": log_entry}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        analysis_str = response.choices[0].message.content
        analysis = json.loads(analysis_str)

        if 'is_anomaly' not in analysis or 'reason' not in analysis or 'ignore_regex' not in analysis:
            raise ValueError("Invalid JSON response from LLM")

    except Exception as e:
        analysis = {
            'is_anomaly': True, # Treat LLM errors as anomalies to be safe
            'reason': f"Error during LLM analysis: {e}",
            'ignore_regex': None
        }

    # 3. Check against user's ignore list AFTER LLM analysis
    # This allows the LLM to see all logs and suggest rules,
    # but still respects the user's choice to ignore an alert.
    if 'ignore' in config:
        for rule in config['ignore']:
            if re.search(rule['regex'], log_entry):
                # User rule overrides LLM's anomaly decision
                analysis['is_anomaly'] = False
                analysis['reason'] = f"LLM analysis overridden by ignore rule '{rule['name']}'"
                break # Stop checking after first match

    return analysis
