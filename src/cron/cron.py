import os
import time

import psycopg
import requests

APP_HOME_URL = os.environ.get("APP_HOME_URL")
MAX_REQUEST_PER_SECOND = 10
ONE_SECOND = 1

USER_EMAIL = 0
USER_ROLE = 1
DOC_NAME = 2
DOC_ID = 3
ORG_DOMAIN = 4
ADD_DATE = 5

brevo_url = "https://api.brevo.com/v3/events"

brevo_headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "api-key": os.environ["BREVO_API_KEY"]
}

with psycopg.connect(conninfo = os.environ["PG_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                l.display_email AS user_email,
                g.name AS user_role,
                d.name AS doc_name,
                d.url_id AS doc_id,
                o.domain AS org_domain,
                gu.created_at AS add_date
            FROM group_users AS gu
            INNER JOIN users AS u
                ON u.id = gu.user_id
            INNER JOIN logins AS l
                ON l.user_id = u.id
            INNER JOIN groups AS g
                ON g.id = gu.group_id
            INNER JOIN acl_rules AS acl
                ON acl.group_id = g.id
            INNER JOIN docs AS d
                on d.id = acl.doc_id
            INNER JOIN workspaces AS w
                on w.id = d.workspace_id
            INNER JOIN orgs AS o
                on o.id = w.org_id
            WHERE gu.created_at >= NOW() - '1 day'::INTERVAL
            AND gu.user_id != d.created_by;
        """)
        new_users_in_docs = cur.fetchall()

def elapsed_time_since(start_time):
    return time.time() - start_time

def get_doc_url(raw_org_domain, doc_id):
    org_domain = raw_org_domain
    if not org_domain:
        org_domain = "docs"
    return f"{APP_HOME_URL}/o/{org_domain}/{doc_id}"

def create_payload(user_in_doc):
    payload = {}
    payload["event_name"] = "added_to_document"
    payload["identifiers"] = {
        "email_id": user_in_doc[USER_EMAIL]
    }
    payload["event_properties"] = {
        "user_role": user_in_doc[USER_ROLE],
        "doc_url": get_doc_url(user_in_doc[ORG_DOMAIN], user_in_doc[DOC_ID]),
        "doc_name": user_in_doc[DOC_NAME],
        "add_date": user_in_doc[ADD_DATE],
    }
    return payload

request_idx = 0
start_time = time.time()

for user_in_doc in new_users_in_docs:
    if elapsed_time_since(start_time) >= ONE_SECOND:
        start_time = time.time()
    elif (request_idx >= MAX_REQUEST_PER_SECOND) and (elapsed_time_since(start_time) < ONE_SECOND):
        time.sleep(elapsed_time_since(start_time))
        request_idx = 0
    brevo_payload = create_payload(user_in_doc)
    response = requests.post(brevo_url, json=brevo_payload, headers=brevo_headers)
    print(response.text)
    request_idx += 1
