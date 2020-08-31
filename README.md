# github_slack_bot
This is a Slack bot for sending PR and comment notifications to Slack or any other chat via webhook

Setup:

```
virtualenv -p`which python3` venv
pip install -r requirements.txt
pre-commit install && pre-commit run --all-files
```


Set a cron job or a scheduled lambda to run like this:

```
*/15 * */1 * * cd path_to_bot && venv/bin/python3 prs.py
```
