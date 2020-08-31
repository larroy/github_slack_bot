#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Webhook / Slack / Chime PR notifier"""

__author__ = "Pedro Larroy"
__version__ = "0.3"

import os
import sys
from github import Github
import requests
import logging
import time
from collections import namedtuple
import pickle
from typing import Any, List
from functional import seq


PRS_PKL = "prs.pkl"
users = set(["gh_user"])
repos = ["gh_user/repo"]
SLACK_HOOK = os.getenv("HOOK_URL", "https://hooks.slack.com/workflows/...")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

TEST_MODE = os.getenv("PRS_TEST", False)


log = logging.getLogger("prs_bot")


def send_hook(txt):
    if TEST_MODE:
        print(txt)
        return True
    if not txt:
        return False
    json = dict()
    json["Content"] = txt
    retries = 4
    while retries > 0:
        r = requests.post(SLACK_HOOK, json=json)
        if r.status_code != 200:
            logging.warn("Request failed with status: {}".format(r))
        else:
            logging.info("Message sent successfully")
            return True
        retries -= 1
        time.sleep(5)
    logging.error("Couldn't send message: {}".format(txt))
    return False


def fmt_pr(pr, *args):
    # s = "* From {} #[{}]({}): {}\nupdated: {} UTC\n".format(pr.user.login, pr.number, pr.html_url, pr.title, pr.updated_at)
    res = []
    res.append("* From {} #{} {} :: {}".format(pr.user.login, pr.number, pr.html_url, pr.title))
    if args:
        res.extend(args)
    return "\n".join(res)


def labelset(pr):
    s = set()
    for label in pr.labels:
        s.add(label.name)
    return s


UpdatedPRReason = namedtuple("UpdatedPRReason", ["pr", "reasons"])


def updated_prs(prs_seq, prs_prev_seq) -> List[UpdatedPRReason]:
    updated = []
    prs = {x.number: x for x in prs_seq}
    prs_prev = {x.number: x for x in prs_prev_seq}
    prn_set = set(prs.keys())
    prn_prev_set = set(prs_prev.keys())
    prns = prn_set.intersection(prn_prev_set)
    for prn in prns:
        prev_pr = prs_prev[prn]
        pr = prs[prn]
        if prev_pr.updated_at < pr.updated_at:
            reasons = []
            if prev_pr.comments != pr.comments:
                prev_c = prev_pr.comments if prev_pr.comments else 0
                cur_c = pr.comments if pr.comments else 0
                reasons.append("{} new comment(s)".format(cur_c - prev_c))
            if prev_pr.commits != pr.commits:
                prev_c = prev_pr.commits if prev_pr.commits else 0
                cur_c = pr.commits if pr.commits else 0
                reasons.append("{} new commit(s)".format(cur_c - prev_c))
            updated.append(UpdatedPRReason(pr, reasons))
    return updated


def new_prs(prs_seq, prs_prev_seq):
    prs = {x.number: x for x in prs_seq}
    prs_prev = {x.number: x for x in prs_prev_seq}
    prn_set = set(prs.keys())
    prn_prev_set = set(prs_prev.keys())
    prn_new = prn_set.difference(prn_prev_set)
    return [prs[prn] for prn in prn_new]


def get_prs(g: Github, members: list):
    prs_members = []
    for repo in repos:
        logging.info("Checking repo {}".format(repo))
        repo = g.get_repo(repo)
        prs = repo.get_pulls()
        added = 0
        for pr in prs:
            # if pr.user.login in members:
            prs_members.append(pr)
            added += 1
        logging.info(f"Added {added} prs.")
    prs_members_sorted = sorted(prs_members, key=lambda x: x.updated_at)
    return prs_members_sorted


def load_prs_prev(file=PRS_PKL):
    prs_prev = []
    try:
        if os.stat(file).st_size > 0:
            with open(file, "rb") as f:
                prs_prev = pickle.load(f)
    except FileNotFoundError:
        pass
    return prs_prev


SerPR = namedtuple("SerPR", ["number", "updated_at", "commits", "comments"])


def serialize(pr) -> SerPR:
    res = SerPR(pr.number, pr.updated_at, pr.commits, pr.comments)
    return res


def save_prs(prs, file=PRS_PKL):
    try:
        os.unlink(file)
    except FileNotFoundError:
        pass

    serialized = seq(prs).map(serialize).list()
    pickle.dump(serialized, open(file, "wb"))


def filter_by_label(prs, label):
    res = []
    for pr in prs:
        labels = labelset(pr)
        if label in labels:
            res.append(pr)
    return res


def prs_to_list_string(prs: List[Any], header: str) -> List[str]:
    res = []
    if not prs:
        return res
    res.append(header)
    for pr in prs:
        res.append(fmt_pr(pr))
    return res


def updated_prs_to_list_string(prs: List[UpdatedPRReason], header: str) -> List[str]:
    res = []
    if not prs:
        return res
    res.append(header)
    for upr in prs:
        reasons = ""
        if upr.reasons:
            reasons = ", ".join(upr.reasons) + "."
            res.append(fmt_pr(upr.pr, reasons))
        else:
            res.append(fmt_pr(upr.pr))
    return res


def main():
    logging.getLogger().setLevel(logging.INFO)

    gh = Github(GITHUB_TOKEN)
    prs = get_prs(gh, users)
    prs_prev = load_prs_prev()
    prs_new = new_prs(prs, prs_prev)
    prs_updated = updated_prs(prs, prs_prev)
    save_prs(prs)

    send_channel = ["🤖 Github Bobby:"]
    send_channel.extend(prs_to_list_string(prs_new, "\U0001F92F New PRS:"))
    send_channel.extend(updated_prs_to_list_string(prs_updated, "\U0001F4AA updated PRS:"))
    # prs_for_review = filter_by_label(prs, 'pr-awaiting-review')
    # prs_for_merge = filter_by_label(prs, 'pr-awaiting-merge')
    # send_channel.extend(prs_to_list_string(prs_for_review, "\U0001F914 PRs waiting for review:"))
    # send_channel.extend(prs_to_list_string(prs_for_merge, "\U0001F3C1 PRs waiting for merge:"))
    if len(send_channel) > 1:
        text = "\n".join(send_channel)
        send_hook(text)
    else:
        log.info("Nothing to send")
    return 0


if __name__ == "__main__":
    sys.exit(main())
